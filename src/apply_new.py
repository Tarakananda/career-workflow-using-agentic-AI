from pathlib import Path
from typing import Any, Optional
import yaml
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from playwright_stealth.stealth import Stealth
from playwright.sync_api import sync_playwright

from src.matcher_v2 import is_recent_job, should_apply, extract_skills_from_text, calculate_weighted_match, get_missing_required_skills
from src.resume import parse_resume, Resume
from src.data_collector import JobDataCollector, ManualApplyCollector
from src.ui import LiveJobTable, JobRow, JobStatus, create_ui


class JobApplier:
    def __init__(
        self,
        session_file: Path = Path("session.json"),
        profile_file: Path = Path("user_profile.yaml"),
        resume_file: Path = Path("CV_Tarakananda_Optimized.pdf"),
        match_threshold: float = None,
        max_days_old: int = 1,
        ui: Optional[LiveJobTable] = None,
        max_parallel: int = 3,
    ):
        self.session_file = session_file
        self.profile = yaml.safe_load(profile_file.read_text())
        self.resume: Resume = parse_resume(resume_file)

        # Use profile's apply_threshold if not explicitly provided
        if match_threshold is None:
            match_threshold = self.profile.get("apply_threshold", 0.8) * 100
        self.match_threshold = match_threshold
        
        # Read new config options from profile
        self.headless_mode = self.profile.get("headless_mode", True)
        self.check_all_jobs = self.profile.get("check_all_jobs", True)
        self.min_skill_match = self.profile.get("min_skill_match", 80)
        self.max_days_old = max_days_old
        self.job_delay = self.profile.get("job_delay_seconds", 2)
        self.max_parallel = self.profile.get("max_parallel_jobs", max_parallel)
        
        # Use profile's min_skill_match if not explicitly provided
        if match_threshold is None:
            match_threshold = self.profile.get("min_skill_match", 80)
        self.match_threshold = match_threshold
        
        self.collector = JobDataCollector()
        self.manual_collector = ManualApplyCollector()
        self.ui = ui

        # Build experience map from resume for answering questions
        self.experience_map = self._build_experience_map()

        # Load user profile Q&A for unknown questions
        self.profile_qa = self._load_profile_qa()
        
        # Chatbot debug flag
        self._chatbot_debug_done = False
        
        # Thread safety for parallel processing
        self._browser_lock = threading.Lock()
        self._context = None
        self._browser = None
        self._playwright = None

    def _build_experience_map(self) -> dict[str, str]:
        """Build a map of skill -> years of experience from resume."""
        exp_map = {}
        for exp in self.resume.experience:
            # Parse years from experience
            years = 0
            try:
                if exp.start_date and exp.end_date:
                    if "present" in exp.end_date.lower() or "current" in exp.end_date.lower():
                        from datetime import datetime
                        start_year = int(exp.start_date[:4])
                        years = datetime.now().year - start_year
                    else:
                        years = int(exp.end_date[:4]) - int(exp.start_date[:4])
            except:
                years = 3  # default

            for skill in exp.skills_used:
                if skill not in exp_map or exp_map[skill] < years:
                    exp_map[skill.lower()] = f"{years} years"

        # Also add from skills list with default
        for skill in self.resume.skills:
            if skill.lower() not in exp_map:
                exp_map[skill.lower()] = "3 years"

        return exp_map

    def _calculate_total_experience(self) -> int:
        """Calculate total years of experience from resume."""
        total_years = 0
        for exp in self.resume.experience:
            try:
                if exp.start_date and exp.end_date:
                    if "present" in exp.end_date.lower() or "current" in exp.end_date.lower():
                        from datetime import datetime
                        start_year = int(exp.start_date[:4])
                        years = datetime.now().year - start_year
                    else:
                        years = int(exp.end_date[:4]) - int(exp.start_date[:4])
                    total_years += years
            except:
                continue
        return max(total_years, 1)

    def _get_current_company(self) -> str:
        """Get current company from resume."""
        for exp in self.resume.experience:
            if exp.end_date and ("present" in exp.end_date.lower() or "current" in exp.end_date.lower()):
                return exp.company
        return ""

    def _clean_question_text(self, text: str) -> str:
        """Clean question text by removing button text and normalizing."""
        text = text.strip()
        # Remove common button texts
        for btn_text in ['Skip this question', 'Save', 'Next', 'Continue', 'Submit', 'Apply']:
            text = text.replace(btn_text, '')
        # Normalize whitespace
        text = ' '.join(text.split())
        return text.lower()

    def _load_profile_qa(self) -> dict[str, str]:
        """Load Q&A from user_profile.yaml for unknown questions."""
        qa = {}
        if "questions" in self.profile:
            for item in self.profile["questions"]:
                if isinstance(item, dict) and "question" in item and "answer" in item:
                    clean_q = self._clean_question_text(item["question"])
                    qa[clean_q] = item["answer"]
        return qa

    def _save_unknown_question(self, question: str) -> None:
        """Save unknown question to user_profile.yaml for user to answer."""
        question = question.strip()
        if not question:
            return

        # Clean question before checking/saving
        clean_question = self._clean_question_text(question)

        # Check if already exists (using cleaned version)
        for item in self.profile.get("questions", []):
            if isinstance(item, dict) and self._clean_question_text(item.get("question", "")) == clean_question:
                return

        if "questions" not in self.profile:
            self.profile["questions"] = []

        self.profile["questions"].append({
            "question": question,  # Save original for reference
            "answer": ""  # User needs to fill this
        })

        with open("user_profile.yaml", "w") as f:
            yaml.dump(self.profile, f, default_flow_style=False)

        print(f"  ⚠ Unknown question saved to user_profile.yaml: {clean_question}")

    def load_session(self) -> list[dict[str, Any]] | None:
        if not self.session_file.exists():
            return None
        import json
        with open(self.session_file, encoding="utf-8") as fh:
            cookies = json.load(fh)
        return cookies if isinstance(cookies, list) and len(cookies) > 0 else None

    def extract_job_description(self, page: Any) -> str:
        """Extract full job description from job detail page."""
        page.wait_for_timeout(2000)

        selectors = [
            "[class*='jd-container']",
            "[class*='job-desc']",
            ".JDContent",
            "[class*='job-description']",
            ".jobDescription",
            "#jobDescription",
            ".jd-content",
            "[data-testid='job-description']",
            "section[class*='job-desc']",
            "div[class*='job-desc']",
        ]

        for sel in selectors:
            elem = page.query_selector(sel)
            if elem:
                text = elem.inner_text().strip()
                if len(text) > 100:
                    return text

        main_selectors = [
            ".job-detail",
            ".job-detail-container",
            "main",
            ".main-content",
        ]

        for sel in main_selectors:
            main = page.query_selector(sel)
            if main:
                text = main.inner_text().strip()
                if len(text) > 200:
                    return text

        return page.inner_text("body")

    def get_posted_date_from_card(self, card: Any) -> str:
        posted_elem = card.query_selector(".job-post-day, [class*='post-day'], [class*='posted']")
        if posted_elem:
            return posted_elem.inner_text().strip()
        return ""

    def get_company_from_card(self, card: Any) -> str:
        company_elem = card.query_selector("a.company, a[class*='company'], .companyName, .subTitle")
        if company_elem:
            return company_elem.inner_text().strip()
        return ""

    def get_experience_from_card(self, card: Any) -> str:
        exp_elem = card.query_selector(".exp, [class*='exp'], .experience, .expwdth")
        if exp_elem:
            return exp_elem.inner_text().strip()
        return ""

    def get_salary_from_card(self, card: Any) -> str:
        """Extract structured salary range from job card."""
        selectors = [
            "[class*='salary']", ".salary", ".sal", ".salary-span",
            "span:has-text('LPA')", "span:has-text('Lacs')",
            "[class*='ctc']", "[class*='salary']",
            ".salary-wrap", ".ctc-wrap"
        ]
        for sel in selectors:
            elem = card.query_selector(sel)
            if elem and elem.is_visible():
                text = elem.inner_text().strip()
                # Extract structured range: "12-15 LPA", "15-20 Lakhs", etc.
                if any(kw in text.lower() for kw in ['lpa', 'lakh', 'lakhs', 'ctc']):
                    return text
        return "N/A"

    def get_location_from_card(self, card: Any) -> str:
        """Extract exact location from job card."""
        selectors = [
            "[class*='location']", ".location", ".locWdth", 
            "[class*='loc']", ".loc-wrap",
            "span:has-text('Hyderabad')", "span:has-text('Bengaluru')",
            "span:has-text('Remote')", "span:has-text('Hybrid')",
            "span:has-text('Chennai')", "span:has-text('Pune')",
            "span:has-text('Mumbai')", "span:has-text('Delhi')"
        ]
        for sel in selectors:
            elem = card.query_selector(sel)
            if elem and elem.is_visible():
                return elem.inner_text().strip()
        return "N/A"

    def is_relevant_title(self, title: str) -> bool:
        relevant_keywords = ["devops", "cloud", "sre", "site reliability", "aws", "azure", "gcp",
                            "kubernetes", "k8s", "docker", "terraform", "ansible", "jenkins",
                            "ci/cd", "infrastructure", "platform", "reliability", "observability",
                            "prometheus", "grafana", "monitoring", "logging", "automation"]

        exclude_patterns = [
            "java developer", "python developer", "full stack", ".net", "dot net",
            "react", "node js", "nodejs", "angular", "vue", "frontend", "backend",
            "salesforce", "sap", "scrum master", "business analyst", "data scientist",
            "data engineer", "ml engineer", "ai engineer", "mlops", "genai", "llm",
            "network engineer", "security engineer", "support engineer", "qa engineer",
            "test engineer", "quality assurance", "php", "laravel", "wordpress",
            "java back end", "java/azure", "java +azure", "springboot", "microservices",
            "python programmer", "python software developer", "python ai",
            "dot net developer", ".net developer", "full stack .net",
            "frappe", "sdet", "playwright", "sap cpi", "inbound sales",
            "business development", "chocolate maker", "walk-in", "ltts",
            "intermediate data science", "software engineer (support)",
        ]

        title_lower = title.lower()

        if any(ex in title_lower for ex in exclude_patterns):
            return False

        if any(kw in title_lower for kw in relevant_keywords):
            return True

        return False

    def _fill_input(self, container: Any, value: str) -> bool:
        """Fill visible input/textarea with value, or select radio/checkbox within container."""
        try:
            # First try text inputs
            input_elem = container.query_selector("input[type='text'], textarea, input:not([type])")
            if input_elem and input_elem.is_visible():
                input_elem.fill(value)
                return True
            # Try to find any visible input
            inputs = container.query_selector_all("input[type='text'], textarea, input:not([type])")
            for inp in inputs:
                if inp.is_visible():
                    inp.fill(value)
                    return True
            
            # Try radio buttons - match value to option text
            value_lower = value.lower()
            # Extract numeric years from value (e.g., "3 years" -> 3)
            import re
            years_match = re.search(r'(\d+)', value)
            target_years = int(years_match.group(1)) if years_match else None
            
            # Look for radio buttons with year ranges
            radio_options = container.query_selector_all("input[type='radio'], label[class*='radio'], div[class*='radio']")
            for opt in radio_options:
                text = opt.inner_text().strip().lower()
                if target_years is not None:
                    # Check if option text contains the target year range
                    # e.g., "3-5 years", "3 years", "2-3", "3+"
                    if f"{target_years}" in text and ("year" in text or "yr" in text):
                        # Click the radio button or its label
                        if opt.get_attribute("type") == "radio":
                            opt.click()
                        else:
                            # Try to find input inside label
                            radio_input = opt.query_selector("input[type='radio']")
                            if radio_input:
                                radio_input.click()
                            else:
                                opt.click()
                        container.page.wait_for_timeout(500) if hasattr(container, 'page') else None
                        return True
            
            # Try checkboxes for yes/no questions
            if value_lower in ['yes', 'true', '1']:
                checkboxes = container.query_selector_all("input[type='checkbox']")
                for cb in checkboxes:
                    if cb.is_visible() and not cb.is_checked():
                        cb.click()
                        container.page.wait_for_timeout(500) if hasattr(container, 'page') else None
                        return True
            
        except Exception as e:
            print(f"  Fill input error: {e}")
            pass
        return False

    def _answer_application_question(self, container: Any, question: str) -> bool:
        """Try to answer an application question based on resume/profile."""
        question_lower = question.lower()

        # Check profile Q&A first
        for q, answer in self.profile_qa.items():
            if q in question_lower:
                if self._fill_input(container, answer):
                    return True

        # Try to match from experience map (skill-specific years)
        # Also handle variations like "azure cloud" -> "azure", "aws cloud" -> "aws"
        skill_aliases = {
            "azure cloud": "azure",
            "aws cloud": "aws",
            "google cloud": "gcp",
            "gcp": "google cloud",
            "k8s": "kubernetes",
            "ci cd": "ci/cd",
            "cicd": "ci/cd",
            "infra as code": "infrastructure as code",
            "iac": "infrastructure as code",
        }
        
        for skill, exp in self.experience_map.items():
            # Direct match
            if skill in question_lower:
                if self._fill_input(container, exp):
                    print(f"  Answered: {question} -> {exp}")
                    return True
            # Alias match
            for alias, target in skill_aliases.items():
                if alias in question_lower and target == skill:
                    if self._fill_input(container, exp):
                        print(f"  Answered (alias): {question} -> {exp}")
                        return True

        # Check for skill-specific experience questions (e.g., "years of experience in X")
        if "years of experience" in question_lower or "experience in" in question_lower:
            for skill, exp in self.experience_map.items():
                if skill in question_lower:
                    # Try text input first
                    if self._fill_input(container, exp):
                        print(f"  Answered (skill-specific): {question} -> {exp}")
                        return True
                    # Try radio button selection
                    import re
                    years_match = re.search(r'(\d+)', exp)
                    if years_match:
                        years = int(years_match.group(1))
                        if self._select_radio_by_years(container, years):
                            print(f"  Answered (radio): {question} -> {exp}")
                            return True

        # Check for common patterns
        if "notice period" in question_lower:
            notice = self.profile.get("notice_period_months", 3)
            if self._fill_input(container, f"{notice} months"):
                return True

        if "current ctc" in question_lower or "current salary" in question_lower:
            ctc = self.profile.get("current_ctc_lpa", 12)
            if self._fill_input(container, f"{ctc} LPA"):
                return True

        if "expected ctc" in question_lower or "expected salary" in question_lower:
            ctc = self.profile.get("expected_ctc_lpa", 12)
            if self._fill_input(container, f"{ctc} LPA"):
                return True

        if "total experience" in question_lower or "years of experience" in question_lower:
            # Try to extract skill from question and match
            skill_matched = False
            for skill, exp in self.experience_map.items():
                if skill in question_lower:
                    if self._fill_input(container, exp):
                        print(f"  Answered: {question} -> {exp}")
                        return True
                    skill_matched = True
            
            # If no specific skill matched, use total experience
            if not skill_matched:
                total_exp = self._calculate_total_experience()
                if self._fill_input(container, f"{total_exp} years"):
                    return True
                # Also try radio button selection for total experience
                if self._select_radio_by_years(container, total_exp):
                    return True

        if "current company" in question_lower or "current employer" in question_lower:
            current = self._get_current_company()
            if current and self._fill_input(container, current):
                return True

        return False

    def _handle_application_form(self, page: Any) -> bool:
        """Handle application form questions after clicking apply."""
        page.wait_for_timeout(5000)

        # Look for question containers - broader search
        question_containers = page.query_selector_all(
            "[class*='question'], [class*='form-field'], [class*='applicant-question'], "
            ".question-wrapper, .form-group, [data-testid*='question'], "
            "label, .field-label, .question-label"
        )

        # Also get all visible input fields with labels
        input_fields = page.query_selector_all("input[type='text'], input[type='number'], input:not([type]), textarea, select")

        all_answered = True
        processed_questions = set()

        # Process question containers
        for container in question_containers:
            try:
                question_text = container.inner_text().strip()
                if not question_text or len(question_text) < 5 or len(question_text) > 500:
                    continue

                # Deduplicate
                q_key = question_text.lower()[:100]
                if q_key in processed_questions:
                    continue
                processed_questions.add(q_key)

                print(f"  Question found: {question_text[:150]}")

                # Try to answer
                answered = self._answer_application_question(container, question_text)

                if not answered:
                    # Check if it's a dropdown/select
                    select_elem = container.query_selector("select")
                    if select_elem:
                        options = select_elem.query_selector_all("option")
                        for opt in options:
                            if opt.get_attribute("value"):
                                select_elem.select_option(opt.get_attribute("value"))
                                answered = True
                                break

                    if not answered:
                        self._save_unknown_question(question_text)
                        all_answered = False
                        print(f"  ⚠ Could not answer: {question_text[:100]}")

            except Exception as e:
                print(f"  Error handling question: {e}")

        # Also check input fields with nearby labels
        for inp in input_fields:
            try:
                if not inp.is_visible():
                    continue

                # Try to find associated label
                inp_id = inp.get_attribute("id")
                label_text = ""

                if inp_id:
                    label = page.query_selector(f"label[for='{inp_id}']")
                    if label:
                        label_text = label.inner_text().strip()

                # Check placeholder
                placeholder = inp.get_attribute("placeholder") or ""

                # Check aria-label
                aria_label = inp.get_attribute("aria-label") or ""

                # Check parent label
                if not label_text:
                    parent = inp.query_selector("xpath=..")
                    if parent:
                        label_text = parent.inner_text().strip()

                combined_text = f"{label_text} {placeholder} {aria_label}".strip()

                if combined_text and len(combined_text) > 5:
                    q_key = combined_text.lower()[:100]
                    if q_key not in processed_questions:
                        processed_questions.add(q_key)
                        print(f"  Field question: {combined_text[:150]}")
                        answered = self._answer_application_question(inp, combined_text)
                        if not answered:
                            self._save_unknown_question(combined_text)
                            all_answered = False
                            print(f"  ⚠ Could not answer field: {combined_text[:100]}")

            except Exception as e:
                print(f"  Error handling field: {e}")

        # Click submit/continue if available
        submit_btn = page.query_selector(
            "button:has-text('Submit'), button:has-text('Continue'), "
            "button:has-text('Next'), button[type='submit'], "
            "[class*='submit'], [class*='continue']"
        )
        if submit_btn and submit_btn.is_visible():
            submit_btn.click()
            page.wait_for_timeout(3000)

        return all_answered

    def _find_apply_button(self, page: Any):
        """Find the first visible apply button."""
        apply_selectors = [
            "button:has-text('Apply on company site')",
            "button#apply-button",
            "button.apply-button",
            "button:has-text('Apply')",
            "a:has-text('Apply')",
            "[class*='apply']:not([class*='save'])",
            "button[id*='apply']",
            "a[id*='apply']",
            ".apply-button",
            "#apply-button",
            "#company-site-button",
            "button.company-site-button",
        ]
        for sel in apply_selectors:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                return btn, sel
        return None, None

    def _is_chatbot_visible(self, page: Any) -> bool:
        """Check if chatbot sidebar is visible."""
        chatbot_selectors = [
            "[class*='chatbot']",
            "[class*='apply-sidebar']",
            "aside[class*='question']",
            "[role='dialog'][class*='apply']",
            "[class*='sidebar'][class*='apply']",
            "div[data-testid*='chatbot']",
            "div[id*='chatbot']",
        ]
        for sel in chatbot_selectors:
            elem = page.query_selector(sel)
            if elem and elem.is_visible():
                return True
        return False

    def _is_application_success(self, page: Any, initial_url: str) -> bool:
        """Check if application was successful (toast, redirect, success message)."""
        try:
            # Check for success toast/message
            success_selectors = [
                "[class*='toast']:has-text('Applied')",
                "[class*='toast']:has-text('Success')",
                "[class*='message']:has-text('Applied')",
                "[class*='alert']:has-text('Applied')",
                "text=Applied successfully",
                "text=Application submitted",
                "text=Application sent",
                "text=Successfully applied",
            ]
            for sel in success_selectors:
                elem = page.query_selector(sel)
                if elem and elem.is_visible():
                    return True
            
            # Check for URL change (redirect to applied page)
            if page.url != initial_url and ("applied" in page.url or "success" in page.url):
                return True
            
            # Check for "Applied" button state change
            applied_btn = page.query_selector("button:has-text('Applied'), button:has-text('Applied')")
            if applied_btn and applied_btn.is_visible():
                return True
            
            # Check for confirmation modal/dialog
            confirm_selectors = [
                "[class*='modal']:has-text('Applied')",
                "[class*='dialog']:has-text('Applied')",
                "[class*='popup']:has-text('Applied')",
            ]
            for sel in confirm_selectors:
                elem = page.query_selector(sel)
                if elem and elem.is_visible():
                    return True
        except Exception:
            pass
        return False

    def click_apply(self, page: Any, context: Any, job_data: dict) -> dict:
        """
        Click apply and detect which of 3 scenarios occurs.
        Returns: {"status": "applied"|"company_site"|"chatbot"|"failed", 
                  "data": job_data, "unanswered": [...], "error": "..."}
        """
        # Dismiss overlays
        self._dismiss_chatbot_overlay(page)
        
        # Find apply button
        btn, sel = self._find_apply_button(page)
        if not btn:
            return {"status": "failed", "data": job_data, "error": "No apply button found"}
        
        print(f"  Found apply button with selector: {sel}")
        
        # Retry click up to 3 times
        for attempt in range(3):
            # Track pages before click
            initial_pages = len(context.pages)
            initial_url = page.url
            
            # Dismiss overlays before each attempt
            self._dismiss_chatbot_overlay(page)
            
            # Re-find button (may have become stale)
            btn, sel = self._find_apply_button(page)
            if not btn:
                return {"status": "failed", "data": job_data, "error": "No apply button found"}
            
            # Click
            try:
                btn.click()
            except Exception as e:
                print(f"  Click attempt {attempt+1} failed: {e}")
                page.wait_for_timeout(2000)
                continue
            
            page.wait_for_timeout(4000)  # Wait for any UI change
            
            # Scenario 2: New tab opened
            if len(context.pages) > initial_pages:
                new_tab = context.pages[-1]
                return self._handle_company_site(new_tab, job_data)
            
            # Scenario 3: Chatbot sidebar on same page
            if self._is_chatbot_visible(page):
                return self._handle_chatbot_questions(page, job_data)
            
            # Scenario 1: Direct apply (redirect or success toast)
            if self._is_application_success(page, initial_url):
                return {"status": "applied", "data": job_data}
            
            # If we reach here, click didn't produce expected result - retry
            if attempt < 2:
                print(f"  Click attempt {attempt+1} didn't produce expected result, retrying...")
                page.wait_for_timeout(2000)
                continue
        
        # Failed after retries
        return {"status": "failed", "data": job_data, "error": "No outcome detected after apply click retries"}

    def _handle_company_site(self, page: Any, job_data: dict) -> dict:
        """Handle 'Apply on company site' - capture for manual apply."""
        try:
            page.wait_for_load_state("domcontentloaded", timeout=30000)
        except Exception:
            pass
        
        # Extract location from JD if not in job_data
        location = self._extract_location_from_jd(job_data.get("jd_text", ""))
        
        manual_record = {
            "role": job_data["role"],
            "title": job_data["title"],
            "company": job_data["company"],
            "posted_date": job_data["posted_date"],
            "experience": job_data["experience"],
            "location": location,
            "match_percentage": job_data["match_percentage"],
            "matched_skills": ", ".join(job_data["matched_skills"]),
            "missing_skills": ", ".join(job_data["missing_skills"]),
            "naukri_url": job_data["url"],
            "company_site_url": page.url,
            "status": "manual_apply_needed",
            "timestamp": datetime.now().isoformat()
        }
        
        self.manual_collector.add_job(manual_record)
        page.close()
        
        return {"status": "company_site", "data": manual_record}

    def _extract_location_from_jd(self, jd_text: str) -> str:
        """Extract location from job description text."""
        import re
        jd_lower = jd_text.lower()
        # Common location patterns
        locations = ["bangalore", "bengaluru", "hyderabad", "chennai", "pune", "mumbai", "delhi", "gurgaon", "noida", "remote", "hybrid"]
        for loc in locations:
            if loc in jd_lower:
                return loc.title()
        return ""

    def _handle_chatbot_questions(self, page: Any, job_data: dict) -> dict:
        """Handle chatbot sidebar questions on job detail page."""
        page.wait_for_timeout(3000)
        
        # Debug dump on first encounter
        if not self._chatbot_debug_done:
            self._debug_dump_sidebar_elements(page)
            self._chatbot_debug_done = True
        
        chatbot = self._find_chatbot_container(page)
        if not chatbot:
            # Try alternative: maybe the chatbot is on the page itself
            print("  Chatbot container not found with standard selectors, trying page-level search...")
            chatbot = page
        
        unanswered = []
        max_iterations = 15
        
        for iteration in range(max_iterations):
            # Re-find chatbot container (may become stale after clicks)
            if iteration > 0:
                chatbot = self._find_chatbot_container(page)
                if not chatbot:
                    chatbot = page
            
            # Get current question
            question = self._get_chatbot_question(chatbot)
            if not question:
                print("  No more questions found")
                break  # No more questions
            
            print(f"  Chatbot Q{iteration+1}: {question[:100]}")
            
            # Try to answer (search within chatbot, not page)
            answered = self._answer_application_question(chatbot, question)
            print(f"  Question answered: {answered}")
            
            if not answered:
                self._save_unknown_question(question)
                unanswered.append(question)
                # Fill placeholder so chatbot can proceed
                self._fill_placeholder_answer(chatbot, question)
            
            # Click Continue/Next with retry
            print("  Attempting to click Continue/Next...")
            if not self._click_chatbot_continue(chatbot):
                # Try alternative: press Enter
                try:
                    if hasattr(chatbot, 'keyboard'):
                        chatbot.keyboard.press("Enter")
                    else:
                        page.keyboard.press("Enter")
                    page.wait_for_timeout(1000)
                except:
                    print("  Enter key press failed")
                    break
            
            page.wait_for_timeout(3000)  # Wait longer for next question to load
            
            # Check if question changed (detect if we're stuck on same question)
            if iteration > 0:
                next_question = self._get_chatbot_question(chatbot)
                if next_question and self._clean_question_text(next_question) == self._clean_question_text(question):
                    print("  WARNING: Question didn't change after Continue click, may be stuck")
                    # Try pressing Enter again
                    try:
                        page.keyboard.press("Enter")
                        page.wait_for_timeout(2000)
                    except:
                        pass
        
        # Click final Submit with retry
        for attempt in range(3):
            if self._click_chatbot_submit(chatbot):
                break
            page.wait_for_timeout(1000)
        
        page.wait_for_timeout(3000)
        
        # Verify success
        if self._is_application_success(page, page.url):
            if unanswered:
                return {"status": "chatbot_partial", "data": job_data, "unanswered": unanswered}
            return {"status": "applied", "data": job_data}
        
        return {"status": "chatbot_failed", "data": job_data, "unanswered": unanswered, 
                "error": "Chatbot did not complete successfully"}

    def _find_chatbot_container(self, page: Any):
        """Find chatbot sidebar container element."""
        chatbot_selectors = [
            "[class*='chatbot']",
            "[class*='apply-sidebar']", 
            "aside[class*='question']",
            "[role='dialog'][class*='apply']",
            "[class*='sidebar'][class*='apply']",
            "div[data-testid*='chatbot']",
            "div[id*='chatbot']",
            "div[class*='questions']",
            "div[class*='apply-form']",
            "div[class*='sidebar']",
            "aside",
            "[class*='overlay'][class*='apply']",
            "div[class*='chat']",
            "div[id*='chat']",
            "[class*='bot']",
            "[data-testid*='chat']",
        ]
        for sel in chatbot_selectors:
            elem = page.query_selector(sel)
            if elem and elem.is_visible():
                print(f"  Found chatbot container with selector: {sel}")
                return elem
        # Fallback: check if any visible element contains chatbot-like text
        try:
            body_text = page.inner_text("body").lower()
            if any(kw in body_text for kw in ['years of experience', 'notice period', 'current ctc', 'expected ctc', 'skip this question', 'crowdstrike', 'how many years']):
                print("  Chatbot-like text found on page, using page as chatbot container")
                return page
        except Exception:
            pass
        return None

    def _get_chatbot_question(self, chatbot) -> str:
        """Extract current question text from chatbot."""
        try:
            # Look for question text in various elements
            question_selectors = [
                "label", "p", "div[class*='question']", "span[class*='question']",
                "[class*='prompt']", "[class*='field']", "h3", "h4",
                "div[class*='text']", "span[class*='text']",
            ]
            for sel in question_selectors:
                elems = chatbot.query_selector_all(sel)
                for el in elems:
                    text = el.inner_text().strip()
                    if text and len(text) > 10 and len(text) < 500:
                        # Check if it looks like a question
                        if any(q in text.lower() for q in ['?', 'years', 'experience', 'notice', 'salary', 'ctc', 'company', 'skill', 'tool', 'technology', 'azure', 'aws', 'cloud', 'terraform', 'ansible', 'kubernetes', 'docker', 'jenkins', 'ci/cd', 'devops']):
                            # Clean up button text
                            clean_text = text
                            for btn_text in ['Skip this question', 'Save', 'Next', 'Continue', 'Submit', 'Apply']:
                                clean_text = clean_text.replace(btn_text, '').strip()
                            if len(clean_text) > 10:
                                return clean_text
            # Fallback: get all text and find question-like part
            all_text = chatbot.inner_text().strip()
            if all_text:
                # Try to extract last sentence that looks like a question
                sentences = [s.strip() for s in all_text.split('.') if s.strip()]
                for s in reversed(sentences):
                    if len(s) > 10 and len(s) < 300 and ('?' in s or any(kw in s.lower() for kw in ['years', 'experience', 'notice', 'salary', 'ctc', 'company', 'skill', 'tool', 'azure', 'aws', 'cloud', 'terraform', 'ansible', 'kubernetes', 'docker', 'jenkins', 'ci/cd', 'devops'])):
                        # Clean up button text
                        for btn_text in ['Skip this question', 'Save', 'Next', 'Continue', 'Submit', 'Apply']:
                            s = s.replace(btn_text, '').strip()
                        if len(s) > 10:
                            return s
        except Exception:
            pass
        return ""

    def _click_chatbot_continue(self, chatbot) -> bool:
        """Click Next/Continue button in chatbot."""
        continue_selectors = [
            "button:has-text('Next')", 
            "button:has-text('Continue')",
            "button:has-text('Submit')", 
            "button:has-text('Apply')",
            "button:has-text('Proceed')",
            "[class*='btn']:has-text('Next')", 
            "[class*='btn']:has-text('Continue')",
            "[class*='btn']:has-text('Submit')",
            "[class*='btn']:has-text('Proceed')",
            "button[type='submit']",
        ]
        for sel in continue_selectors:
            btn = chatbot.query_selector(sel)
            if btn and btn.is_visible():
                try:
                    print(f"  Clicking Continue button: {sel}")
                    btn.click()
                    return True
                except Exception as e:
                    print(f"  Continue click failed: {e}")
                    continue
        print("  No Continue button found")
        return False

    def _click_chatbot_submit(self, chatbot) -> bool:
        """Click final Submit button in chatbot."""
        submit_selectors = [
            "button:has-text('Submit')", 
            "button:has-text('Apply')",
            "button:has-text('Finish')",
            "button:has-text('Done')",
            "[class*='btn']:has-text('Submit')",
            "[class*='btn']:has-text('Apply')",
            "button[type='submit']",
        ]
        for sel in submit_selectors:
            btn = chatbot.query_selector(sel)
            if btn and btn.is_visible():
                try:
                    btn.click()
                    return True
                except Exception:
                    continue
        return False

    def _fill_placeholder_answer(self, chatbot, question: str) -> None:
        """Fill placeholder for unanswered question - try text input or radio buttons."""
        try:
            # Try text input first
            input_elem = chatbot.query_selector("input[type='text'], textarea, input:not([type])")
            if input_elem and input_elem.is_visible():
                input_elem.fill("NEEDS_MANUAL_INPUT")
                return
            
            # Try radio buttons - select first available
            radios = chatbot.query_selector_all("input[type='radio']")
            for radio in radios:
                if radio.is_visible() and not radio.is_checked():
                    radio.click()
                    return
        except Exception:
            pass

    def _select_radio_by_years(self, chatbot, years: int) -> bool:
        """Select radio button based on years of experience."""
        try:
            # Find all radio buttons and their labels
            radio_groups = chatbot.query_selector_all("input[type='radio']")
            for radio in radio_groups:
                if not radio.is_visible():
                    continue
                
                # Get the label text associated with this radio
                radio_id = radio.get_attribute("id")
                label_text = ""
                
                if radio_id:
                    label = chatbot.query_selector(f"label[for='{radio_id}']")
                    if label:
                        label_text = label.inner_text().strip().lower()
                
                # Also check parent label
                if not label_text:
                    parent = radio.query_selector("xpath=..")
                    if parent:
                        label_text = parent.inner_text().strip().lower()
                
                # Check if this radio option matches our years
                # Common patterns: "0-1", "1-3", "3-5", "5+", "0-1 years", "1-3 years", etc.
                if label_text:
                    import re
                    # Check for ranges like "0-1", "1-3", "3-5", "5+"
                    range_match = re.search(r'(\d+)\s*[-–]\s*(\d+)', label_text)
                    if range_match:
                        min_years = int(range_match.group(1))
                        max_years = int(range_match.group(2))
                        if min_years <= years <= max_years:
                            radio.click()
                            return True
                    
                    # Check for "X+" pattern
                    plus_match = re.search(r'(\d+)\s*\+\s*years?', label_text)
                    if plus_match:
                        min_years = int(plus_match.group(1))
                        if years >= min_years:
                            radio.click()
                            return True
                    
                    # Check for "X years" pattern
                    years_match = re.search(r'(\d+)\s*years?', label_text)
                    if years_match:
                        option_years = int(years_match.group(1))
                        if option_years == years:
                            radio.click()
                            return True
                    
                    # Check for "less than X" or "under X"
                    if "less than" in label_text or "under" in label_text:
                        under_match = re.search(r'(\d+)', label_text)
                        if under_match:
                            max_years = int(under_match.group(1))
                            if years < max_years:
                                radio.click()
                                return True
                    
                    # Check for "more than X" or "over X"
                    if "more than" in label_text or "over" in label_text:
                        over_match = re.search(r'(\d+)', label_text)
                        if over_match:
                            min_years = int(over_match.group(1))
                            if years > min_years:
                                radio.click()
                                return True
            
            # Fallback: click first available radio
            for radio in radio_groups:
                if radio.is_visible() and not radio.is_checked():
                    radio.click()
                    return True
                    
        except Exception as e:
            print(f"  Radio selection error: {e}")
        return False

    def _debug_dump_sidebar_elements(self, page: Any) -> None:
        """Dump all potential chatbot/sidebar elements for selector tuning."""
        import os
        os.makedirs("txt_output", exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        debug_file = f"txt_output/chatbot_debug_{timestamp}.txt"
        
        selectors = [
            "[class*='chatbot']", "[class*='sidebar']", "[class*='apply']",
            "aside", "[role='dialog']", "[class*='panel']", "[class*='drawer']",
            "[class*='question']", "[class*='form']", "[data-testid*='apply']"
        ]
        
        with open(debug_file, "w") as f:
            f.write("=== CHATBOT DEBUG: Potential sidebar elements ===\n\n")
            for sel in selectors:
                elems = page.query_selector_all(sel)
                for i, el in enumerate(elems):
                    if el.is_visible():
                        try:
                            html = el.get_attribute("outerHTML")[:500]
                            f.write(f"  [{sel}] #{i}: {html}\n\n")
                        except Exception:
                            pass
            f.write("=== END DEBUG ===\n")
        
        print(f"  Chatbot debug saved to {debug_file}")

    def _dismiss_chatbot_overlay(self, page: Any) -> None:
        """Dismiss chatbot/widget overlays that intercept clicks."""
        try:
            # Common chatbot overlay selectors on Naukri
            overlay_selectors = [
                "div.chatbot_Overlay",
                "div[class*='chatbot_Overlay']",
                "div._chatBotContainer",
                "div[class*='chatBotContainer']",
                "button[class*='close']:has-text('×')",
                "button[aria-label*='close' i]",
                "button[aria-label*='dismiss' i]",
                "[class*='overlay']:has-text('×')",
            ]
            for sel in overlay_selectors:
                overlay = page.query_selector(sel)
                if overlay and overlay.is_visible():
                    # Try to find close button within overlay
                    close_btn = overlay.query_selector("button, [role='button'], a")
                    if close_btn and close_btn.is_visible():
                        close_btn.click()
                        page.wait_for_timeout(500)
                        print(f"  Dismissed chatbot overlay: {sel}")
                        return
                    # Try clicking overlay itself to dismiss
                    try:
                        overlay.click(position={"x": 10, "y": 10})  # Click corner
                        page.wait_for_timeout(500)
                        print(f"  Clicked overlay corner to dismiss: {sel}")
                        return
                    except:
                        pass
            # Try pressing Escape key to dismiss any modal
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
        except Exception as e:
            print(f"  Chatbot dismiss attempt failed: {e}")

    def _close_job_tab_safely(self, job_page: Any, search_page: Any) -> None:
        """Safely close job detail tab and return to search results."""
        try:
            if job_page:
                job_page.close()
            search_page.wait_for_timeout(1000)  # Let search page stabilize
            # Dismiss chatbot overlay if it appeared
            self._dismiss_chatbot_overlay(search_page)
        except Exception:
            # Fallback: close any extra tabs
            try:
                from playwright.sync_api import sync_playwright
                # Context is available through search_page
                context = search_page.context
                while len(context.pages) > 1:
                    extra_page = context.pages[-1]
                    if extra_page != search_page:
                        extra_page.close()
            except Exception:
                pass

    def sort_by_date(self, page: Any) -> None:
        """Sort search results by date with verification and retry."""
        max_retries = 2
        for attempt in range(max_retries):
            try:
                print(f"  Sorting by date (attempt {attempt + 1})...")
                page.wait_for_selector("#filter-sort", timeout=30000)
                sort_btn = page.query_selector("#filter-sort")
                if sort_btn and sort_btn.is_visible():
                    sort_btn.click()
                    page.wait_for_timeout(3000)
                    # Use text-based selector since data-id might not be on the <a>
                    date_option = page.query_selector("[data-filter-id='sort'] a:has-text('Date'), [data-filter-id='sort'] li:has-text('Date')")
                    if not date_option:
                        date_option = page.query_selector("a[data-id='filter-sort-f']")
                    if not date_option:
                        # Try finding by text in any element within the dropdown
                        date_option = page.query_selector("[data-filter-id='sort'] *:has-text('Date')")
                    if date_option and date_option.is_visible():
                        date_option.click()
                        page.wait_for_selector("[data-job-id], .jobTuple, .job-card", timeout=30000)
                        
                        # Verify sort worked by checking first job date
                        page.wait_for_timeout(2000)
                        first_card = page.query_selector("[data-job-id], .jobTuple, .job-card")
                        if first_card:
                            posted_elem = first_card.query_selector(".job-post-day, [class*='post-day'], [class*='posted']")
                            if posted_elem:
                                posted_text = posted_elem.inner_text().strip().lower()
                                print(f"  First job posted: {posted_text}")
                                if any(kw in posted_text for kw in ['just now', 'hour', 'hr', 'today', 'min']):
                                    print("  ✓ Sort by date verified - showing recent jobs")
                                    return
                        
                        print("  Sorted by date (verification skipped)")
                        return
                    else:
                        print("  Date option not found")
                else:
                    print("  Sort button not found")
            except Exception as e:
                print(f"  Sort by date attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    page.wait_for_timeout(3000)
        print("  Sort by date failed after retries")

    def _apply_location_filters(self, page: Any) -> None:
        """Apply location filters from user profile."""
        locations = self.profile.get("preferred_locations", [])
        if not locations:
            return

        try:
            print(f"  Applying location filters: {locations}")
            location_btn = page.query_selector("button:has-text('Location'), span:has-text('Location'), [data-filter-id='location']")
            if location_btn:
                # Scroll into view first
                location_btn.scroll_into_view_if_needed()
                page.wait_for_timeout(1000)
                if location_btn.is_visible():
                    location_btn.click()
                    page.wait_for_timeout(2000)

                    for loc in locations:
                        loc_elem = page.query_selector(f"label:has-text('{loc}'), span:has-text('{loc}'), input[value='{loc}']")
                        if loc_elem and loc_elem.is_visible():
                            print(f"  Selecting location: {loc}")
                            loc_elem.click()
                            page.wait_for_timeout(500)
                        else:
                            print(f"  Location not found: {loc}")

                    # Close dropdown with Escape key (don't click Apply button - crashes browser)
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(3000)
                    # Wait for results to reload after filter
                    page.wait_for_selector("[data-job-id], .jobTuple, .job-card", timeout=30000)
                    print("  Location filters applied")
            else:
                print("  Location filter button not found")
        except Exception as e:
            print(f"  Location filter skipped: {e}")

    def process_role(self, page: Any, keyword: str, max_jobs: int, context: Any) -> dict:
        """Process a single role: search, filter, check each job, apply if match."""
        base_url = f"https://www.naukri.com/{keyword.lower().replace(' ', '-').replace('&', '')}-jobs"
        search_url = f"{base_url}?experience=3"
        
        if self.ui:
            self.ui.console.print(f"\n[bold cyan]{'='*60}[/bold cyan]")
            self.ui.console.print(f"[bold cyan]Processing role: {keyword}[/bold cyan]")
            self.ui.console.print(f"[bold cyan]URL: {search_url}[/bold cyan]")
            self.ui.console.print(f"[bold cyan]{'='*60}[/bold cyan]")
        else:
            print(f"\n{'='*60}")
            print(f"Processing role: {keyword}")
            print(f"URL: {search_url}")
            print(f"{'='*60}")

        applied = []
        skipped = []
        errors = []
        processed = 0

        # Load search page ONCE
        page.goto(search_url, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_selector("[data-job-id], .jobTuple, .job-card", timeout=30000)

        # Dismiss chatbot overlay if present on search page
        self._dismiss_chatbot_overlay(page)

        # Ensure NO tabs are open except the main search page
        while len(context.pages) > 1:
            try:
                extra_page = context.pages[-1]
                if extra_page != page:
                    extra_page.close()
            except Exception:
                break

        # Apply filters ONCE - location first, then sort by date
        self._apply_location_filters(page)
        self.sort_by_date(page)

        # Verify sort is applied by checking first job date
        page.wait_for_timeout(2000)
        first_card = page.query_selector("[data-job-id], .jobTuple, .job-card")
        if first_card:
            posted_elem = first_card.query_selector(".job-post-day, [class*='post-day'], [class*='posted']")
            if posted_elem:
                posted_text = posted_elem.inner_text().strip().lower()
                if self.ui:
                    self.ui.console.print(f"  Verified first job posted: {posted_text}")
                else:
                    print(f"  Verified first job posted: {posted_text}")

        # Dismiss chatbot again after filters (may reappear)
        self._dismiss_chatbot_overlay(page)

        # Get initial job cards AFTER filters and sort are applied
        cards = page.query_selector_all("[data-job-id], .jobTuple, .job-card")
        total_cards = len(cards)
        if self.ui:
            self.ui.console.print(f"Found {total_cards} job cards after filters and sort")
        else:
            print(f"Found {total_cards} job cards after filters and sort")

        # Use parallel processing if max_parallel > 1
        if self.max_parallel > 1:
            return self._process_role_parallel(page, keyword, max_jobs, context, cards, total_cards)
        
        card_index = 0
        while processed < max_jobs and card_index < len(cards):
            # Close any extra tabs (keep only the main search page)
            while len(context.pages) > 1:
                try:
                    extra_page = context.pages[-1]
                    if extra_page != page:
                        extra_page.close()
                except Exception:
                    break
            
            # Re-query cards if stale (after tab operations)
            try:
                card = cards[card_index]
                # Test if card is still attached
                _ = card.is_visible()
            except Exception:
                # Stale element - re-query
                cards = page.query_selector_all("[data-job-id], .jobTuple, .job-card")
                if card_index >= len(cards):
                    if self.ui:
                        self.ui.console.print("No more cards to process")
                    else:
                        print("No more cards to process")
                    break
                card = cards[card_index]

            try:
                # Get title and posted date from card
                title_elem = card.query_selector("a.title, a[class*='title'], h2 a, h3 a, .job-title a")
                link_elem = card.query_selector("a[href*='job-'], a[href*='/job/'], a.title")

                if not title_elem or not link_elem:
                    card_index += 1
                    continue

                title = title_elem.inner_text().strip()
                url = link_elem.get_attribute("href")
                posted = self.get_posted_date_from_card(card)
                company = self.get_company_from_card(card)
                experience = self.get_experience_from_card(card)

                # Check if recent
                if not is_recent_job(posted, self.max_days_old):
                    if self.ui:
                        row = self.ui.add_job(card_index, title)
                        self.ui.update_job(card_index, status=JobStatus.SKIPPED_OLD)
                        self.ui.increment_processed(JobStatus.SKIPPED_OLD)
                    else:
                        print(f"  [{card_index+1}] Skip (old): {title[:50]} | Posted: {posted}")
                    card_index += 1
                    continue

                # Check if relevant title (only if check_all_jobs is False)
                if not self.check_all_jobs and not self.is_relevant_title(title):
                    if self.ui:
                        row = self.ui.add_job(card_index, title)
                        self.ui.update_job(card_index, status=JobStatus.SKIPPED_IRRELEVANT)
                        self.ui.increment_processed(JobStatus.SKIPPED_IRRELEVANT)
                    else:
                        print(f"  [{card_index+1}] Skip (irrelevant): {title[:50]} | Posted: {posted}")
                    card_index += 1
                    continue

                # Create UI row for this job
                if self.ui:
                    row = self.ui.add_job(card_index, title)
                    self.ui.update_job(card_index, company=company, experience=experience, status=JobStatus.FETCHING)
                else:
                    print(f"\n  [{card_index+1}] Checking: {title[:60]}")
                    print(f"      Posted: {posted}")
                    print(f"      Company: {company}")
                    print(f"      Experience: {experience}")
                    print(f"      URL: {url}")

                # Click job to open detail page in NEW TAB (with retry)
                job_page = None
                for attempt in range(3):
                    try:
                        with context.expect_page() as new_page_info:
                            link_elem.click()
                        job_page = new_page_info.value
                        job_page.wait_for_load_state("domcontentloaded", timeout=30000)
                        job_page.wait_for_selector("[class*='jd-container'], .job-desc, .JDContent", timeout=30000)
                        break
                    except Exception as e:
                        if self.ui:
                            self.ui.update_job(card_index, status=JobStatus.ERROR, error_msg=f"Open failed: {e}")
                        else:
                            print(f"      ✗ Failed to open job (attempt {attempt+1}/3): {e}")
                        if job_page:
                            try:
                                job_page.close()
                            except:
                                pass
                        if attempt == 2:
                            if self.ui:
                                self.ui.update_job(card_index, status=JobStatus.ERROR, error_msg=f"Open failed after 3 attempts: {e}")
                                self.ui.increment_processed(JobStatus.ERROR)
                            else:
                                print(f"      ✗ Failed to open job after 3 attempts: {e}")
                            errors.append({"title": title, "url": url, "error": str(e)})
                            card_index += 1
                            continue
                        page.wait_for_timeout(2000)
                
                if not job_page:
                    card_index += 1
                    continue

                # Extract JD and check skills from new tab (with timeout and error handling)
                job_data = None
                try:
                    if self.ui:
                        self.ui.update_job(card_index, status=JobStatus.ANALYZING)
                    
                    jd_text = self.extract_job_description(job_page)
                    jd_text = jd_text[:5000]

                    job_skills = extract_skills_from_text(jd_text)
                    
                    # Use optimized skills from profile for matching (expanded for >80% match)
                    resume_skills = self.profile.get("optimized_skills", self.resume.skills)
                    
                    should, match_pct, matched, missing = should_apply(
                        resume_skills, jd_text, self.match_threshold
                    )

                    if self.ui:
                        self.ui.update_job(card_index, match_pct=match_pct, missing_skills=missing[:5])
                    else:
                        print(f"      Skills in JD: {job_skills[:10]}")
                        print(f"      Match: {match_pct:.1f}% | Matched: {matched} | Missing: {missing[:5]}")

                    # Get salary and location from card
                    salary = self.get_salary_from_card(card)
                    location = self.get_location_from_card(card)

                    # Collect job data for output file
                    job_data = {
                        "role": keyword,
                        "title": title,
                        "company": company,
                        "experience": experience,
                        "posted_date": posted,
                        "url": url,
                        "salary": salary,
                        "location": location,
                        "jd_text": jd_text,
                        "jd_skills": job_skills,
                        "resume_skills": resume_skills,
                        "matched_skills": matched,
                        "missing_skills": missing,
                        "match_percentage": round(match_pct, 1),
                        "applied": False,
                        "status": "skipped" if not should else "applied",
                        "error": None
                    }

                    if should:
                        if self.ui:
                            self.ui.update_job(card_index, salary=salary, location=location, status=JobStatus.APPLYING)
                        else:
                            print(f"      ✓ Match > {self.match_threshold}%, applying...")
                            # Wait for apply button to be ready - use loop with query_selector
                            apply_btn = None
                            for attempt in range(15):
                                job_page.wait_for_timeout(1000)
                                apply_btn = job_page.query_selector("#apply-button")
                                if apply_btn:
                                    print(f"  Attempt {attempt+1}: Apply button found via query_selector, is_visible={apply_btn.is_visible()}, url={job_page.url}")
                                    break
                                else:
                                    print(f"  Attempt {attempt+1}: Apply button not found yet, url={job_page.url}")

                        # Use new click_apply with outcome detection
                        result = self.click_apply(job_page, context, job_data)
                        
                        if result["status"] == "applied":
                            applied.append({
                                "title": title,
                                "url": url,
                                "match_pct": match_pct,
                                "posted": posted
                            })
                            job_data["applied"] = True
                            job_data["status"] = "applied"
                            print(f"      ✓ Applied successfully")
                        elif result["status"] == "company_site":
                            applied.append({
                                "title": title,
                                "url": url,
                                "match_pct": match_pct,
                                "posted": posted
                            })
                            job_data["applied"] = True
                            job_data["status"] = "company_site"
                            if self.ui:
                                self.ui.update_job(card_index, salary=salary, location=location, status=JobStatus.COMPANY_SITE)
                                self.ui.increment_processed(JobStatus.COMPANY_SITE)
                            else:
                                print(f"      → Company site opened, added to manual apply list")
                        elif result["status"] == "chatbot":
                            applied.append({
                                "title": title,
                                "url": url,
                                "match_pct": match_pct,
                                "posted": posted
                            })
                            job_data["applied"] = True
                            job_data["status"] = "applied"
                            if self.ui:
                                self.ui.update_job(card_index, salary=salary, location=location, status=JobStatus.APPLIED)
                                self.ui.increment_processed(JobStatus.APPLIED)
                            else:
                                print(f"      ✓ Applied via chatbot")
                        elif result["status"] == "chatbot_partial":
                            # Unanswered questions = failed per requirement
                            errors.append({
                                "title": title,
                                "url": url,
                                "error": f"Chatbot unanswered questions: {result['unanswered']}"
                            })
                            job_data["status"] = "failed"
                            job_data["error"] = f"Chatbot unanswered questions: {result['unanswered']}"
                            if self.ui:
                                self.ui.update_job(card_index, status=JobStatus.SKIPPED_QUESTIONS, error_msg="Unanswered questions")
                                self.ui.increment_processed(JobStatus.SKIPPED_QUESTIONS)
                            else:
                                print(f"      ✗ Chatbot incomplete - unanswered questions")
                        else:
                            errors.append({
                                "title": title,
                                "url": url,
                                "error": result.get("error", "Apply failed")
                            })
                            job_data["status"] = "error"
                            job_data["error"] = result.get("error", "Apply failed")
                            if self.ui:
                                self.ui.update_job(card_index, status=JobStatus.ERROR, error_msg=result.get("error", "Apply failed")[:40])
                                self.ui.increment_processed(JobStatus.ERROR)
                            else:
                                print(f"      ✗ Apply failed: {result.get('error', 'Unknown')}")
                    else:
                        skipped.append({
                            "title": title,
                            "url": url,
                            "match_pct": match_pct,
                            "missing": missing,
                            "posted": posted
                        })
                        if self.ui:
                            self.ui.update_job(card_index, salary=salary, location=location, status=JobStatus.SKIPPED_MISMATCH)
                            self.ui.increment_processed(JobStatus.SKIPPED_MISMATCH)
                        else:
                            print(f"      ✗ Match < {self.match_threshold}%, skipping")

                    self.collector.add_job(job_data)
                    processed += 1

                except Exception as e:
                    if self.ui:
                        self.ui.update_job(card_index, status=JobStatus.ERROR, error_msg=str(e)[:40])
                        self.ui.increment_processed(JobStatus.ERROR)
                    else:
                        print(f"      ✗ Error processing JD: {e}")
                    errors.append({"title": title, "url": url, "error": str(e)})
                    if job_data:
                        job_data["status"] = "error"
                        job_data["error"] = str(e)
                        self.collector.add_job(job_data)

                finally:
                    # ALWAYS close job detail tab - robust cleanup
                    self._close_job_tab_safely(job_page, page)

                card_index += 1

                # Rate limiting delay between jobs
                if self.job_delay > 0:
                    page.wait_for_timeout(self.job_delay * 1000)

            except Exception as e:
                if self.ui:
                    self.ui.update_job(card_index, status=JobStatus.ERROR, error_msg=str(e)[:40])
                    self.ui.increment_processed(JobStatus.ERROR)
                else:
                    print(f"  ✗ Error with card {card_index}: {e}")
                card_index += 1
                continue

        if processed == 0:
            if self.ui:
                self.ui.console.print("No matching jobs found to process")
            else:
                print("No matching jobs found to process")

        return {"applied": applied, "skipped": skipped, "errors": errors}

    def _process_role_parallel(self, page: Any, keyword: str, max_jobs: int, context: Any, cards: list, total_cards: int) -> dict:
        """Process jobs in parallel using multiple browser contexts."""
        from playwright.sync_api import sync_playwright
        
        applied = []
        skipped = []
        errors = []
        processed = 0
        
        # Create a semaphore to limit concurrent jobs
        semaphore = threading.Semaphore(self.max_parallel)
        results_lock = threading.Lock()
        
        def process_single_job(card_index: int) -> dict:
            """Process a single job card in its own browser context."""
            with semaphore:
                # Create new browser context for this job
                with self._browser_lock:
                    if not self._playwright:
                        return {"error": "Browser not initialized"}
                    job_context = self._browser.new_context()
                    job_context.add_cookies(context.cookies())
                    job_page = job_context.new_page()
                    job_page.set_default_timeout(60000)
                    job_page.set_default_navigation_timeout(90000)
                
                try:
                    # Re-find the card in the new context (navigate to search page)
                    base_url = f"https://www.naukri.com/{keyword.lower().replace(' ', '-').replace('&', '')}-jobs"
                    search_url = f"{base_url}?experience=3"
                    job_page.goto(search_url, wait_until="domcontentloaded", timeout=90000)
                    job_page.wait_for_selector("[data-job-id], .jobTuple, .job-card", timeout=30000)
                    self._apply_location_filters(job_page)
                    self.sort_by_date(job_page)
                    job_page.wait_for_timeout(2000)
                    
                    job_cards = job_page.query_selector_all("[data-job-id], .jobTuple, .job-card")
                    if card_index >= len(job_cards):
                        return {"error": "Card index out of range", "skipped": True}
                    
                    card = job_cards[card_index]
                    
                    # Get title and posted date from card
                    title_elem = card.query_selector("a.title, a[class*='title'], h2 a, h3 a, .job-title a")
                    link_elem = card.query_selector("a[href*='job-'], a[href*='/job/'], a.title")

                    if not title_elem or not link_elem:
                        return {"error": "No title/link element", "skipped": True}

                    title = title_elem.inner_text().strip()
                    url = link_elem.get_attribute("href")
                    posted = self.get_posted_date_from_card(card)
                    company = self.get_company_from_card(card)
                    experience = self.get_experience_from_card(card)

                    # Check if recent
                    if not is_recent_job(posted, self.max_days_old):
                        return {"skipped": True, "reason": "old", "title": title, "posted": posted}

                    # Check if relevant title
                    if not self.check_all_jobs and not self.is_relevant_title(title):
                        return {"skipped": True, "reason": "irrelevant", "title": title, "posted": posted}

                    # Click job to open detail page
                    job_detail_page = None
                    for attempt in range(3):
                        try:
                            with job_context.expect_page() as new_page_info:
                                link_elem.click()
                            job_detail_page = new_page_info.value
                            job_detail_page.wait_for_load_state("domcontentloaded", timeout=30000)
                            job_detail_page.wait_for_selector("[class*='jd-container'], .job-desc, .JDContent", timeout=30000)
                            break
                        except Exception as e:
                            if job_detail_page:
                                try:
                                    job_detail_page.close()
                                except:
                                    pass
                            if attempt == 2:
                                return {"error": f"Failed to open job: {e}", "title": title, "url": url}
                            job_page.wait_for_timeout(2000)
                    
                    if not job_detail_page:
                        return {"error": "No job detail page", "title": title, "url": url}

                    try:
                        jd_text = self.extract_job_description(job_detail_page)
                        jd_text = jd_text[:5000]

                        job_skills = extract_skills_from_text(jd_text)
                        resume_skills = self.profile.get("optimized_skills", self.resume.skills)
                        
                        should, match_pct, matched, missing = should_apply(
                            resume_skills, jd_text, self.match_threshold
                        )

                        salary = self.get_salary_from_card(card)
                        location = self.get_location_from_card(card)

                        job_data = {
                            "role": keyword,
                            "title": title,
                            "company": company,
                            "experience": experience,
                            "posted_date": posted,
                            "url": url,
                            "salary": salary,
                            "location": location,
                            "jd_text": jd_text,
                            "jd_skills": job_skills,
                            "resume_skills": resume_skills,
                            "matched_skills": matched,
                            "missing_skills": missing,
                            "match_percentage": round(match_pct, 1),
                            "applied": False,
                            "status": "skipped" if not should else "applied",
                            "error": None
                        }

                        if should:
                            result = self.click_apply(job_detail_page, job_context, job_data)
                            
                            if result["status"] == "applied":
                                return {"applied": True, "title": title, "url": url, "match_pct": match_pct, "posted": posted, "job_data": job_data}
                            elif result["status"] == "company_site":
                                return {"applied": True, "title": title, "url": url, "match_pct": match_pct, "posted": posted, "job_data": job_data, "company_site": True}
                            elif result["status"] == "chatbot":
                                return {"applied": True, "title": title, "url": url, "match_pct": match_pct, "posted": posted, "job_data": job_data}
                            elif result["status"] == "chatbot_partial":
                                return {"error": f"Chatbot unanswered questions: {result['unanswered']}", "title": title, "url": url, "job_data": job_data}
                            else:
                                return {"error": result.get("error", "Apply failed"), "title": title, "url": url, "job_data": job_data}
                        else:
                            return {"skipped": True, "reason": "mismatch", "title": title, "url": url, "match_pct": match_pct, "missing": missing, "posted": posted, "job_data": job_data}

                    except Exception as e:
                        return {"error": str(e), "title": title, "url": url}
                    finally:
                        self._close_job_tab_safely(job_detail_page, job_page)
                        job_context.close()

                except Exception as e:
                    return {"error": str(e), "title": title if 'title' in locals() else "Unknown"}
                finally:
                    try:
                        job_context.close()
                    except:
                        pass

        # Collect card indices to process
        card_indices = list(range(min(max_jobs, total_cards)))
        
        # Process in parallel
        with ThreadPoolExecutor(max_workers=self.max_parallel) as executor:
            future_to_index = {executor.submit(process_single_job, idx): idx for idx in card_indices}
            
            for future in as_completed(future_to_index):
                result = future.result()
                
                with results_lock:
                    processed += 1
                    
                    if result.get("applied"):
                        applied.append({
                            "title": result["title"],
                            "url": result["url"],
                            "match_pct": result["match_pct"],
                            "posted": result["posted"]
                        })
                        if self.ui:
                            status = JobStatus.COMPANY_SITE if result.get("company_site") else JobStatus.APPLIED
                            self.ui.increment_processed(status)
                        job_data = result.get("job_data", {})
                        job_data["applied"] = True
                        job_data["status"] = "company_site" if result.get("company_site") else "applied"
                        self.collector.add_job(job_data)
                    elif result.get("skipped"):
                        skipped.append({
                            "title": result["title"],
                            "url": result.get("url", ""),
                            "match_pct": result.get("match_pct", 0),
                            "missing": result.get("missing", []),
                            "posted": result.get("posted", "")
                        })
                        if self.ui:
                            if result.get("reason") == "old":
                                self.ui.increment_processed(JobStatus.SKIPPED_OLD)
                            elif result.get("reason") == "irrelevant":
                                self.ui.increment_processed(JobStatus.SKIPPED_IRRELEVANT)
                            else:
                                self.ui.increment_processed(JobStatus.SKIPPED_MISMATCH)
                        job_data = result.get("job_data", {})
                        if job_data:
                            self.collector.add_job(job_data)
                    elif result.get("error"):
                        errors.append({
                            "title": result.get("title", "Unknown"),
                            "url": result.get("url", ""),
                            "error": result["error"]
                        })
                        if self.ui:
                            self.ui.increment_processed(JobStatus.ERROR)
                        job_data = result.get("job_data", {})
                        if job_data:
                            job_data["status"] = "error"
                            job_data["error"] = result["error"]
                            self.collector.add_job(job_data)

        if processed == 0:
            if self.ui:
                self.ui.console.print("No matching jobs found to process")
            else:
                print("No matching jobs found to process")

        return {"applied": applied, "skipped": skipped, "errors": errors}

    def run(self, max_jobs_per_role: int = 10) -> dict:
        """Run the full pipeline: process each role sequentially."""
        cookies = self.load_session()
        if not cookies:
            raise RuntimeError("No valid session. Run login.py first.")

        keywords = self.profile.get("strict_roles", [])

        all_applied = []
        all_skipped = []
        all_errors = []

        # Initialize UI if provided
        if self.ui:
            self.ui.start()

        with sync_playwright() as p:
            Stealth().use_sync(p)
            browser = p.chromium.launch(headless=self.headless_mode)
            
            # Store for parallel processing
            self._playwright = p
            self._browser = browser
            self._context = browser.new_context()
            self._context.add_cookies(cookies)
            page = self._context.new_page()
            
            # Set longer timeout for headless mode
            page.set_default_timeout(60000)
            page.set_default_navigation_timeout(90000)

            try:
                for keyword in keywords:
                    result = self.process_role(page, keyword, max_jobs_per_role, self._context)
                    all_applied.extend(result["applied"])
                    all_skipped.extend(result["skipped"])
                    all_errors.extend(result["errors"])

                    if self.ui:
                        self.ui.console.print(f"\n[bold green]Role '{keyword}' complete: Applied={len(result['applied'])}, Skipped={len(result['skipped'])}, Errors={len(result['errors'])}[/bold green]")
                    else:
                        print(f"\nRole '{keyword}' complete: Applied={len(result['applied'])}, Skipped={len(result['skipped'])}, Errors={len(result['errors'])}")

                    # Small delay between roles
                    page.wait_for_timeout(2000)

            finally:
                browser.close()
                self._playwright = None
                self._browser = None
                self._context = None

        # Stop UI and show final summary
        if self.ui:
            self.ui.stop()
            self.ui.print_final_summary()
        else:
            # Print table and save file
            self.collector.print_table()
        
        filepath = self.collector.save()

        # Save manual apply Excel
        if self.manual_collector.jobs_data:
            if self.ui:
                self.ui.console.print("\n[bold cyan]Manual Apply Jobs:[/bold cyan]")
                self.manual_collector.print_table()
            else:
                self.manual_collector.print_table()
            self.manual_collector.save_excel()

        return {
            "applied": all_applied,
            "skipped": all_skipped,
            "errors": all_errors,
            "output_file": str(filepath)
        }


def main():
    from src.search import JobSearch

    ui = create_ui()
    applier = JobApplier(ui=ui, max_parallel=3)
    result = applier.run(max_jobs_per_role=10)

    # Final summary is now printed by UI


if __name__ == "__main__":
    main()