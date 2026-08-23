from pathlib import Path
from typing import Any, Optional
import yaml
from datetime import datetime
import threading
import os

from playwright_stealth.stealth import Stealth
from playwright.sync_api import sync_playwright

from src.matcher_v2 import is_recent_job, extract_skills_from_text
from src.resume import parse_resume, Resume
from src.data_collector import JobDataCollector, ManualApplyCollector
from src.ui import LiveJobTable, JobRow, JobStatus, create_ui
from src.llm_extractor import LLMSkillExtractor, extract_skill_inventory
from src.chatbot_answerer_sync import ChatbotAnswerer, create_chatbot_answerer


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
            match_threshold = self.profile.get("apply_threshold", 0.75) * 100
        self.match_threshold = match_threshold
        
        # Read new config options from profile
        self.headless_mode = self.profile.get("headless_mode", True)
        self.check_all_jobs = self.profile.get("check_all_jobs", True)
        self.min_skill_match = self.profile.get("min_skill_match", 80)
        self.max_days_old = max_days_old
        self.job_delay = self.profile.get("job_delay_seconds", 2)
        self.max_parallel = self.profile.get("max_parallel_jobs", max_parallel)
        self.minimize_browser = self.profile.get("minimize_browser", True)
        
        # LLM config
        self.llm_model = self.profile.get("llm_model", "gpt-4o-mini")
        self.openai_api_key = self.profile.get("openai_api_key") or os.getenv("OPENAI_API_KEY")
        
        self.collector = JobDataCollector()
        self.manual_collector = ManualApplyCollector()
        self.ui = ui

        # Build experience map from resume for answering questions
        self.experience_map = self._build_experience_map()

        # Load user profile Q&A for unknown questions
        self.profile_qa = self._load_profile_qa()
        
        # Initialize LLM-based skill extractor and chatbot answerer
        print("  Initializing LLM skill extractor...")
        self.skill_inventory = self._build_skill_inventory()
        
        # Build experience map for chatbot
        self.experience_map = self._build_experience_map()
        
        self.chatbot_answerer = create_chatbot_answerer(
            skill_inventory=self.skill_inventory,
            profile_qa=self.profile_qa,
            profile=self.profile,
            api_key=self.openai_api_key,
            ui=self.ui,
            experience_map=self.experience_map
        )
        
        # Chatbot debug flag
        self._chatbot_debug_done = False

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

    def _build_skill_inventory(self) -> dict[str, str]:
        """Build comprehensive skill inventory using LLM extraction from resume."""
        resume_path = Path("CV_Tarakananda_Optimized.pdf")
        if not resume_path.exists():
            resume_path = Path("CV_Tarakananda.pdf")
        
        try:
            return extract_skill_inventory(resume_path, api_key=self.openai_api_key)
        except Exception as e:
            print(f"  LLM skill extraction failed: {e}, using fallback")
            # Fallback to experience_map
            return self.experience_map.copy()

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
        
        # Extract must-have and good-to-have skills from JD
        from src.matcher_v2 import SKILL_CATEGORIES, extract_skills_from_text
        jd_skills = extract_skills_from_text(job_data.get("jd_text", ""))
        must_have = [s for s in jd_skills if any(s in cat.skills for cat in SKILL_CATEGORIES if cat.required)]
        good_to_have = [s for s in jd_skills if any(s in cat.skills for cat in SKILL_CATEGORIES if not cat.required)]
        
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
            "must_have_skills": must_have,
            "good_to_have_skills": good_to_have,
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
        """Handle chatbot sidebar questions on job detail page.
        
        Flow based on screenshots:
        1. Dialog opens with a question and radio buttons
        2. Select radio option (Yes/No or experience range)
        3. "Save" button becomes enabled
        4. Click "Save" to go to next question
        5. Repeat for all questions
        6. "Applied" confirmation appears
        """
        page.wait_for_timeout(3000)
        
        # Debug dump on first encounter
        if not self._chatbot_debug_done:
            self._debug_dump_sidebar_elements(page)
            self._chatbot_debug_done = True
        
        chatbot = self._find_chatbot_container(page)
        if not chatbot:
            if self.ui:
                self.ui.console.print("  [Chatbot] Container not found with standard selectors, trying page-level search...")
            else:
                print("  Chatbot container not found with standard selectors, trying page-level search...")
            chatbot = page
        
        unanswered = []
        max_iterations = 20
        
        for iteration in range(max_iterations):
            # Re-find chatbot container (may become stale after clicks)
            if iteration > 0:
                chatbot = self._find_chatbot_container(page)
                if not chatbot:
                    chatbot = page
            
            # Get current question
            question = self._get_chatbot_question(chatbot)
            if not question:
                if self.ui:
                    self.ui.console.print("  [Chatbot] No more questions found")
                else:
                    print("  No more questions found")
                break  # No more questions
            
            if self.ui:
                self.ui.console.print(f"  [Chatbot] Q{iteration+1}: {question[:100]}")
            else:
                print(f"  Chatbot Q{iteration+1}: {question[:100]}")
            
            # Try to answer (search within chatbot, not page)
            answered = self.chatbot_answerer.answer_question(question, chatbot, page)
            
            if not answered:
                self._save_unknown_question(question)
                unanswered.append(question)
                # Fill placeholder so chatbot can proceed
                self._fill_placeholder_answer(chatbot, question)
            
            # Wait a bit for Save button to enable after radio selection
            page.wait_for_timeout(2000)
            
            # Click "Save" button (not Continue) - this is what the screenshots show
            if self.ui:
                self.ui.console.print("  [Chatbot] Attempting to click Save...")
            else:
                print("  Attempting to click Save...")
            
            if not self._click_chatbot_save(chatbot, page):
                if self.ui:
                    self.ui.console.print("  [Chatbot] Save button not found, trying Enter...")
                else:
                    print("  Save button not found, trying Enter...")
                try:
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(1000)
                except:
                    if self.ui:
                        self.ui.console.print("  [Chatbot] Enter key press failed")
                    else:
                        print("  Enter key press failed")
                    break
            
            page.wait_for_timeout(3000)  # Wait for next question to load
            
            # Check if question changed (detect if we're stuck on same question)
            if iteration > 0:
                next_question = self._get_chatbot_question(chatbot)
                if next_question and self._clean_question_text(next_question) == self._clean_question_text(question):
                    if self.ui:
                        self.ui.console.print("  [Chatbot] WARNING: Question didn't change after Save click, may be stuck")
                    else:
                        print("  WARNING: Question didn't change after Save click, may be stuck")
                    
                    # Track consecutive same questions
                    if not hasattr(self, '_same_question_count'):
                        self._same_question_count = 0
                    self._same_question_count += 1
                    
                    if self._same_question_count >= 2:
                        # Try different answer format for text input questions
                        if "write na" in question.lower() or "write n/a" in question.lower():
                            print("  [Chatbot] Trying different answer format (N/A)...")
                            # The chatbot might expect "N/A" instead of "NA"
                            # We'll handle this in the next iteration by the chatbot_answerer
                        if self._same_question_count >= 3:
                            if self.ui:
                                self.ui.console.print("  [Chatbot] Stuck on same question, breaking loop")
                            else:
                                print("  Stuck on same question, breaking loop")
                            break
                    
                    # Try pressing Enter again
                    try:
                        page.keyboard.press("Enter")
                        page.wait_for_timeout(2000)
                    except:
                        pass
        
        # After all questions, verify "Applied" success
        page.wait_for_timeout(3000)
        
        # Verify success - check for "Applied" text or success indicators
        if self._is_application_success(page, page.url):
            if unanswered:
                return {"status": "chatbot_partial", "data": job_data, "unanswered": unanswered}
            return {"status": "applied", "data": job_data}
        
        return {"status": "chatbot_failed", "data": job_data, "unanswered": unanswered, 
                "error": "Chatbot did not complete successfully"}

    def _click_chatbot_save(self, chatbot, page: Any = None) -> bool:
        """Click Save button in chatbot dialog. Searches both chatbot container and full page.
        Waits for form submission and verifies next question appears."""
        save_selectors = [
            "button:has-text('Save')", 
            "button:has-text('Save & Continue')",
            "button:has-text('Save and Continue')",
            "[class*='btn']:has-text('Save')",
            "button[type='submit']",
            "input[type='submit'][value*='Save']",
            "button[aria-label*='Save']",
            "[data-testid*='save']",
        ]
        
        # Search in chatbot container first, then full page
        search_contexts = [chatbot]
        if page:
            search_contexts.append(page)
        
        for ctx in search_contexts:
            for sel in save_selectors:
                btn = ctx.query_selector(sel)
                if btn and btn.is_visible():
                    try:
                        # Check if button is disabled
                        is_disabled = btn.get_attribute("disabled") or btn.get_attribute("aria-disabled") == "true"
                        if is_disabled:
                            print(f"  Button found but disabled: {sel}")
                            continue
                        print(f"  Clicking Save button: {sel}")
                        btn.click()
                        # Wait for form submission / next question to appear
                        page.wait_for_timeout(3000)
                        # Check if question changed (form submitted)
                        try:
                            new_question = self._get_chatbot_question(chatbot)
                            if new_question:
                                print(f"  [Chatbot] Form submitted, next question: {new_question[:50]}")
                            else:
                                print(f"  [Chatbot] No question found after submit")
                        except:
                            pass
                        return True
                    except Exception as e:
                        print(f"  Save click failed: {e}")
                        continue
        print("  No Save button found")
        return False

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

    def _click_chatbot_continue(self, chatbot, page: Any = None) -> bool:
        """Click Next/Continue button in chatbot. Searches both chatbot container and full page."""
        continue_selectors = [
            "button:has-text('Next')", 
            "button:has-text('Continue')",
            "button:has-text('Submit')", 
            "button:has-text('Apply')",
            "button:has-text('Proceed')",
            "button:has-text('Save & Continue')",
            "button:has-text('Save and Continue')",
            "[class*='btn']:has-text('Next')", 
            "[class*='btn']:has-text('Continue')",
            "[class*='btn']:has-text('Submit')",
            "[class*='btn']:has-text('Proceed')",
            "button[type='submit']",
            "input[type='button'][value*='Continue']",
            "input[type='button'][value*='Next']",
            "input[type='submit'][value*='Continue']",
            "input[type='submit'][value*='Next']",
            "button[aria-label*='Continue']",
            "button[aria-label*='Next']",
            "[data-testid*='continue']",
            "[data-testid*='next']",
        ]
        
        # Search in chatbot container first, then full page
        search_contexts = [chatbot]
        if page:
            search_contexts.append(page)
        
        for ctx in search_contexts:
            for sel in continue_selectors:
                btn = ctx.query_selector(sel)
                if btn and btn.is_visible():
                    try:
                        # Check if button is disabled
                        is_disabled = btn.get_attribute("disabled") or btn.get_attribute("aria-disabled") == "true"
                        if is_disabled:
                            print(f"  Button found but disabled: {sel}")
                            continue
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
            "button:has-text('Complete')",
            "[class*='btn']:has-text('Submit')",
            "[class*='btn']:has-text('Apply')",
            "[class*='btn']:has-text('Finish')",
            "button[type='submit']",
            "input[type='submit'][value*='Submit']",
            "input[type='submit'][value*='Apply']",
            "button[aria-label*='Submit']",
            "button[aria-label*='Finish']",
        ]
        for sel in submit_selectors:
            btn = chatbot.query_selector(sel)
            if btn and btn.is_visible():
                try:
                    is_disabled = btn.get_attribute("disabled") or btn.get_attribute("aria-disabled") == "true"
                    if is_disabled:
                        continue
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
                try:
                    # Check if job_page is still valid before closing
                    job_page.evaluate("() => true")
                    job_page.close()
                except Exception:
                    pass
            search_page.wait_for_timeout(1000)  # Let search page stabilize
            # Dismiss chatbot overlay if it appeared
            self._dismiss_chatbot_overlay(search_page)
        except Exception:
            # Fallback: close any extra tabs
            try:
                context = search_page.context
                while len(context.pages) > 1:
                    extra_page = context.pages[-1]
                    if extra_page != search_page:
                        extra_page.close()
            except Exception:
                pass

    def sort_by_date(self, page: Any) -> None:
        """Sort search results by date with verification and retry - ROBUST version."""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if self.ui:
                    self.ui.console.print(f"  [Sort] Sorting by date (attempt {attempt + 1}/{max_retries})...")
                else:
                    print(f"  Sorting by date (attempt {attempt + 1}/{max_retries})...")
                
                # Wait for sort button with longer timeout
                page.wait_for_selector("#filter-sort", timeout=60000)
                sort_btn = page.query_selector("#filter-sort")
                
                if sort_btn and sort_btn.is_visible():
                    sort_btn.click()
                    page.wait_for_timeout(3000)
                    
                    # Multiple strategies to find the Date option
                    date_option = None
                    
                    # Strategy 1: data-filter-id with text
                    date_option = page.query_selector("[data-filter-id='sort'] a:has-text('Date'), [data-filter-id='sort'] li:has-text('Date')")
                    
                    # Strategy 2: data-id attribute
                    if not date_option:
                        date_option = page.query_selector("a[data-id='filter-sort-f']")
                    
                    # Strategy 3: any element within dropdown with "Date" text
                    if not date_option:
                        date_option = page.query_selector("[data-filter-id='sort'] *:has-text('Date')")
                    
                    # Strategy 4: broader search - any visible element with "Date" in sort dropdown area
                    if not date_option:
                        # Try clicking the sort button again to reopen dropdown
                        sort_btn.click()
                        page.wait_for_timeout(2000)
                        date_option = page.query_selector(":has-text('Date'):visible")
                    
                    if date_option and date_option.is_visible():
                        date_option.click()
                        page.wait_for_selector("[data-job-id], .jobTuple, .job-card", timeout=60000)
                        
                        # Verify sort worked by checking first job date
                        page.wait_for_timeout(3000)
                        first_card = page.query_selector("[data-job-id], .jobTuple, .job-card")
                        if first_card:
                            posted_elem = first_card.query_selector(".job-post-day, [class*='post-day'], [class*='posted']")
                            if posted_elem:
                                posted_text = posted_elem.inner_text().strip().lower()
                                if self.ui:
                                    self.ui.console.print(f"  [Sort] First job posted: {posted_text}")
                                else:
                                    print(f"  First job posted: {posted_text}")
                                if any(kw in posted_text for kw in ['just now', 'hour', 'hr', 'today', 'min', 'sec']):
                                    if self.ui:
                                        self.ui.console.print("  ✓ [Sort] Sort by date verified - showing recent jobs")
                                    else:
                                        print("  ✓ Sort by date verified - showing recent jobs")
                                    return
                        
                        if self.ui:
                            self.ui.console.print("  [Sort] Sorted by date (verification skipped)")
                        else:
                            print("  Sorted by date (verification skipped)")
                        return
                    else:
                        if self.ui:
                            self.ui.console.print("  [Sort] Date option not found")
                        else:
                            print("  Date option not found")
                else:
                    if self.ui:
                        self.ui.console.print("  [Sort] Sort button not found")
                    else:
                        print("  Sort button not found")
            except Exception as e:
                if self.ui:
                    self.ui.console.print(f"  [Sort] Sort by date attempt {attempt + 1} failed: {e}")
                else:
                    print(f"  Sort by date attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    page.wait_for_timeout(5000)
        if self.ui:
            self.ui.console.print("  [Sort] Sort by date failed after retries")
        else:
            print("  Sort by date failed after retries")

    def _apply_location_filters(self, page: Any) -> None:
        """Apply location filters from user profile - radio buttons in left sidebar filters."""
        # Location variants mapping
        LOCATION_VARIANTS = {
            "Bengaluru": ["Bengaluru", "Bangalore", "Bengaluru Urban", "Bengaluru Rural"],
            "Hyderabad": ["Hyderabad", "Secunderabad", "Hyderabad Secunderabad"],
        }
        
        def _normalize_location(loc: str) -> str:
            """Map location variants to canonical name"""
            loc_lower = loc.lower()
            for canonical, variants in LOCATION_VARIANTS.items():
                if any(v.lower() in loc_lower for v in variants):
                    return canonical
            return loc

        locations = self.profile.get("preferred_locations", [])
        if not locations:
            if self.ui:
                self.ui.console.print("  [Location] No preferred locations configured")
            else:
                print("  No preferred locations configured")
            return

        if self.ui:
            self.ui.console.print(f"  [Location] Applying filters (radio buttons): {locations}")
        else:
            print(f"  Applying location filters (radio buttons): {locations}")

        try:
            # Find and click the location filter button to expand
            location_btn = page.query_selector("button:has-text('Location'), span:has-text('Location'), [data-filter-id='location']")
            if location_btn:
                location_btn.scroll_into_view_if_needed()
                page.wait_for_timeout(1000)
                if location_btn.is_visible():
                    location_btn.click()
                    page.wait_for_timeout(5000)  # Longer wait for dropdown to fully expand

                    success_count = 0
                    for loc in locations:
                        canonical = _normalize_location(loc)
                        variants = LOCATION_VARIANTS.get(canonical, [canonical])
                        
                        selected = False
                        for variant in variants:
                            # These are RADIO BUTTONS in the left sidebar filters
                            # Try multiple approaches to find and click the radio button
                            radio = None
                            
                            # Approach 1: Find radio button by value in left sidebar (aside)
                            radio = page.query_selector(f"aside input[type='radio'][value*='{variant}']")
                            if radio and radio.is_visible():
                                radio.scroll_into_view_if_needed()
                                radio.evaluate("el => el.click()")
                                page.wait_for_timeout(1000)
                                selected = True
                                break
                            
                            # Approach 2: Find label by text in left sidebar and click it
                            if not selected:
                                label = page.query_selector(f"aside label:has-text('{variant}')")
                                if label and label.is_visible():
                                    label.scroll_into_view_if_needed()
                                    label.click()
                                    page.wait_for_timeout(1000)
                                    selected = True
                                    break
                            
                            # Approach 3: Find radio button by value anywhere
                            if not selected:
                                radio = page.query_selector(f"input[type='radio'][value*='{variant}']")
                                if radio and radio.is_visible():
                                    radio.scroll_into_view_if_needed()
                                    radio.evaluate("el => el.click()")
                                    page.wait_for_timeout(1000)
                                    selected = True
                                    break
                            
                            # Approach 4: Find by text and click
                            if not selected:
                                label = page.query_selector(f"text={variant}")
                                if label and label.is_visible():
                                    label.scroll_into_view_if_needed()
                                    label.click()
                                    page.wait_for_timeout(1000)
                                    selected = True
                                    break
                        
                        if selected:
                            if self.ui:
                                self.ui.console.print(f"  [Location] Selected: {loc}")
                            else:
                                print(f"  Selected location: {loc}")
                            success_count += 1
                        else:
                            if self.ui:
                                self.ui.console.print(f"  [Location] Not found: {loc}")
                            else:
                                print(f"  Location not found: {loc}")

            # Close dropdown with Escape key
            page.keyboard.press("Escape")
            page.wait_for_timeout(3000)
            
            # Wait for results to reload
            page.wait_for_selector("[data-job-id], .jobTuple, .job-card", timeout=60000)
            
            if self.ui:
                self.ui.console.print(f"  [Location] Filters applied ({success_count}/{len(locations)} found)")
            else:
                print(f"  Location filters applied ({success_count}/{len(locations)} found)")
        except Exception as e:
            if self.ui:
                self.ui.console.print(f"  [Location] Filter error: {e}")
            else:
                print(f"  Location filter error: {e}")

    def _normalize_location(self, loc: str) -> str:
        """Map location variants to canonical name"""
        LOCATION_VARIANTS = {
            "Bengaluru": ["Bengaluru", "Bangalore", "Bengaluru Urban", "Bengaluru Rural"],
            "Hyderabad": ["Hyderabad", "Secunderabad", "Hyderabad Secunderabad"],
        }
        loc_lower = loc.lower()
        for canonical, variants in LOCATION_VARIANTS.items():
            if any(v.lower() in loc_lower for v in variants):
                return canonical
        return loc

    def process_role(self, page: Any, keyword: str, max_jobs: int, context: Any) -> dict:
        """Process a single role: search, filter, process ALL cards sequentially.
        Uses cityTypeGid URL parameters for location filtering (single source of truth).
        """
        # CityTypeGid mapping for preferred locations
        CITY_TYPE_GID = {
            "Bengaluru": 17,
            "Bangalore": 17,
            "Hyderabad": 97,
            "Secunderabad": 97,
        }
        
        base_url = f"https://www.naukri.com/{keyword.lower().replace(' ', '-').replace('&', '')}-jobs"
        
        # Build URL with cityTypeGid parameters for preferred locations
        locations = self.profile.get("preferred_locations", [])
        city_gids = []
        for loc in locations:
            for canonical, gid in CITY_TYPE_GID.items():
                if loc.lower() == canonical.lower():
                    city_gids.append(str(gid))
                    break
        
        # Build URL with experience=3 and cityTypeGid params
        params = ["experience=3"]
        for gid in city_gids:
            params.append(f"cityTypeGid={gid}")
        search_url = f"{base_url}?{'&'.join(params)}"
        
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

        # Load search page ONCE - URL already has location filters
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

        # URL already has location filters via cityTypeGid params
        # Just sort by date
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

        # Get initial job cards AFTER sort is applied
        cards = page.query_selector_all("[data-job-id], .jobTuple, .job-card")
        total_cards = len(cards)
        if self.ui:
            self.ui.console.print(f"Found {total_cards} job cards after filters and sort")
        else:
            print(f"Found {total_cards} job cards after filters and sort")

        # Track existing signatures for duplicate detection (within this run)
        existing_signatures = set()
        for job in self.collector.jobs_data:
            sig = self._create_job_signature(job)
            existing_signatures.add(sig)

        applied = []
        skipped = []
        errors = []
        processed = 0

        # Process ALL cards (max_jobs is ignored - process all cards)
        for card_index in range(total_cards):
            # Verify main page is still valid
            try:
                page.evaluate("() => true")
            except Exception:
                print("  Main page closed unexpectedly, stopping")
                break
            
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
                cards = page.query_selector_all("[data-job-id], .jobTuple, .job-card")
                if card_index >= len(cards):
                    if self.ui:
                        self.ui.console.print("No more cards to process")
                    else:
                        print("No more cards to process")
                    break
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
                    continue

                title = title_elem.inner_text().strip()
                url = link_elem.get_attribute("href")
                posted = self.get_posted_date_from_card(card)

                # AGE CHECK: Jobs >1 day - DON'T OPEN CARD, skip immediately
                if not is_recent_job(posted, self.max_days_old):
                    job_data = {
                        "role": keyword, "title": title, "company": "", 
                        "location": "", "experience": "", "posted_date": posted,
                        "url": url, "must_have_skills": [], "good_to_have_skills": [],
                        "matched_skills": [], "missing_skills": [], 
                        "match_percentage": 0, "jd_text": "",
                        "status": "skipped_old", "error": f"Posted: {posted}",
                        "applied": False
                    }
                    self._record_job(job_data, "skipped_old", f"Posted: {posted}")
                    if self.ui:
                        self.ui.increment_processed(JobStatus.SKIPPED_OLD)
                    continue

                # Create UI row for this job
                if self.ui:
                    row = self.ui.add_job(card_index, title)
                    self.ui.update_job(card_index, status=JobStatus.FETCHING)
                else:
                    print(f"\n  [{card_index+1}] Checking: {title[:60]}")
                    print(f"      Posted: {posted}")
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
                            break
                        page.wait_for_timeout(2000)
                
                if not job_page:
                    continue

                # Initialize job_data before try block to avoid undefined variable in except
                job_data = {
                    "role": keyword,
                    "title": title,
                    "company": "",
                    "location": "",
                    "experience": "",
                    "posted_date": posted,
                    "url": url,
                    "must_have_skills": [],
                    "good_to_have_skills": [],
                    "matched_skills": [],
                    "missing_skills": [],
                    "match_percentage": 0,
                    "jd_text": "",
                }
                
                try:
                    if self.ui:
                        self.ui.update_job(card_index, status=JobStatus.ANALYZING)
                    
                    # EXTRACT COMPLETE JOB DETAILS FROM JD PAGE
                    job_details = self._extract_complete_job_details(job_page, keyword, url, posted)
                    
                    # Update job_data with extracted details
                    job_data["title"] = job_details["title"]
                    job_data["company"] = job_details["company"]
                    job_data["location"] = job_details["location"]
                    job_data["experience"] = job_details["experience"]
                    job_data["posted_date"] = job_details["posted_date"]
                    job_data["jd_text"] = job_details["jd_text"][:5000]
                    
                    # Check location match (preferred locations only)
                    location_match = self._check_location_match(job_details["location"])
                    
                    # SKILL MATCHING: Based ONLY on must-have + good-to-have skills from JD
                    resume_skills = self.profile.get("optimized_skills", self.resume.skills)
                    
                    # Extract must-have and good-to-have skills from JD
                    jd_skills = extract_skills_from_text(job_details["jd_text"])
                    from src.matcher_v2 import SKILL_CATEGORIES
                    jd_must_have = [s for s in jd_skills if any(s in cat.skills for cat in SKILL_CATEGORIES if cat.required)]
                    jd_good_to_have = [s for s in jd_skills if any(s in cat.skills for cat in SKILL_CATEGORIES if not cat.required)]
                    
                    # Calculate match percentage based ONLY on must-have + good-to-have skills
                    all_jd_skills = set(jd_must_have + jd_good_to_have)
                    resume_set = set(resume_skills)
                    
                    matched_must = resume_set & set(jd_must_have)
                    matched_good = resume_set & set(jd_good_to_have)
                    missing_must = set(jd_must_have) - resume_set
                    missing_good = set(jd_good_to_have) - resume_set
                    
                    total_required = len(jd_must_have) + len(jd_good_to_have)
                    total_matched = len(matched_must) + len(matched_good)
                    
                    # Must have 100% of must-have skills, 80% overall
                    must_have_pct = (len(matched_must) / len(jd_must_have) * 100) if jd_must_have else 100
                    overall_pct = (total_matched / total_required * 100) if total_required > 0 else 100
                    
                    should = (must_have_pct >= 100 and overall_pct >= 80) if jd_must_have else (overall_pct >= 80)
                    match_pct = overall_pct
                    
                    matched = list(matched_must) + list(matched_good)
                    missing = list(missing_must) + list(missing_good)
                    must_have = list(matched_must)
                    good_to_have = list(matched_good)
                    
                    # Update job_data with skill info
                    job_data["must_have_skills"] = must_have
                    job_data["good_to_have_skills"] = good_to_have
                    job_data["matched_skills"] = matched
                    job_data["missing_skills"] = missing
                    job_data["match_percentage"] = round(match_pct, 1)
                    
                    # DUPLICATE CHECK: Exact match on 4 fields (title + company + must_have + good_to_have)
                    job_signature = self._create_job_signature(job_data)
                    if job_signature in existing_signatures:
                        if self.ui:
                            self.ui.update_job(card_index, status=JobStatus.SKIPPED_IRRELEVANT, error_msg="Duplicate")
                        else:
                            print(f"  [{card_index+1}] Duplicate skipped: {title[:50]} (already processed)")
                        self._record_job(job_data, "duplicate")
                        job_page.close()
                        continue
                    
                    # Add signature to existing set to prevent future duplicates in this run
                    existing_signatures.add(self._create_job_signature(job_data))
                    
                    # DETERMINE STATUS & ACTION
                    if not location_match:
                        status = "skipped_location"
                        error_msg = f"Location: {job_details['location']} (not preferred)"
                    elif not should:
                        status = "skipped_mismatch"
                        error_msg = f"Missing: {', '.join(missing[:5])}"
                    else:
                        # SKILLS MATCH + LOCATION MATCH → APPLY
                        if self.ui:
                            self.ui.update_job(card_index, status=JobStatus.APPLYING, 
                                              must_have_skills=must_have, good_to_have_skills=good_to_have)
                        else:
                            print(f"      ✓ Match > {self.match_threshold}%, applying...")
                        
                        # Wait for apply button
                        apply_btn = None
                        for attempt in range(15):
                            job_page.wait_for_timeout(1000)
                            apply_btn = job_page.query_selector("#apply-button")
                            if apply_btn:
                                break
                        
                        # Use click_apply with outcome detection
                        result = self.click_apply(job_page, context, job_data)
                        
                        if result["status"] in ["applied", "chatbot", "company_site"]:
                            status = result["status"]
                            applied.append({
                                "title": job_data["title"],
                                "url": url,
                                "match_pct": match_pct,
                                "posted": posted
                            })
                        else:
                            status = "error"
                            error_msg = result.get("error", "Apply failed")
                    
                    # Record job with complete data
                    job_data["status"] = status
                    job_data["error"] = error_msg if status not in ["applied", "chatbot", "company_site", "duplicate"] else None
                    job_data["applied"] = status in ["applied", "chatbot", "company_site"]
                    self._record_job(job_data, status, error_msg if status not in ["applied", "chatbot", "company_site", "duplicate"] else None)
                    
                    if status in ["applied", "chatbot", "company_site"]:
                        applied.append({"title": job_data["title"], "url": url, "match_pct": match_pct, "posted": posted})
                    elif status != "duplicate":
                        skipped.append({"title": job_data["title"], "url": url, "match_pct": match_pct, "posted": posted})
                    
                    processed += 1
                    
                except Exception as e:
                    if self.ui:
                        self.ui.update_job(card_index, status=JobStatus.ERROR, error_msg=str(e)[:40])
                    else:
                        print(f"      ✗ Error processing JD: {e}")
                    errors.append({"title": title, "url": url, "error": str(e)})
                    if job_data:
                        job_data["status"] = "error"
                        job_data["error"] = str(e)
                        self._record_job(job_data, "error", str(e))
                    
                finally:
                    # ALWAYS close job detail tab - robust cleanup
                    self._close_job_tab_safely(job_page, page)
                
                # Rate limiting delay between jobs
                if self.job_delay > 0:
                    page.wait_for_timeout(self.job_delay * 1000)
            
            except Exception as e:
                if self.ui:
                    self.ui.update_job(card_index, status=JobStatus.ERROR, error_msg=str(e)[:40])
                    self.ui.increment_processed(JobStatus.ERROR)
                else:
                    print(f"  ✗ Error with card {card_index}: {e}")
                continue

        if processed == 0:
            if self.ui:
                self.ui.console.print("No matching jobs found to process")
            else:
                print("No matching jobs found to process")

        return {"applied": applied, "skipped": skipped, "errors": errors}

    def _create_job_signature(self, job_data: dict) -> str:
        """Create unique signature for duplicate detection
        Based on: Title + Company + Must-have skills + Good-to-have skills
        """
        key_parts = [
            job_data.get("title", "").strip().lower(),
            job_data.get("company", "").strip().lower(),
            ",".join(sorted(job_data.get("must_have_skills", []))),
            ",".join(sorted(job_data.get("good_to_have_skills", []))),
        ]
        return "|".join(key_parts)

    def _check_location_match(self, job_location: str) -> bool:
        """Check if job location has Hyderabad OR Bengaluru/Bangalore OR Remote.
        Job proceeds if ANY of these three are available.
        Job skips ONLY if NONE of the three are available.
        """
        job_loc_lower = job_location.lower()
        
        # Check for Hyderabad
        hyderabad_terms = ["hyderabad", "secunderabad"]
        has_hyderabad = any(term in job_loc_lower for term in hyderabad_terms)
        
        # Check for Bengaluru/Bangalore
        bangalore_terms = ["bengaluru", "bangalore"]
        has_bangalore = any(term in job_loc_lower for term in bangalore_terms)
        
        # Check for Remote
        remote_terms = ["remote", "work from home", "wfh"]
        has_remote = any(term in job_loc_lower for term in remote_terms)
        
        # Proceed if ANY of the three are available
        return has_hyderabad or has_bangalore or has_remote

    def _extract_complete_job_details(self, job_page, keyword, url, posted) -> dict:
        """Extract ALL job details from JD page"""
        jd_text = self.extract_job_description(job_page)
        
        # Extract company from JD page
        company = ""
        company_selectors = [
            ".company-name", "[class*='company']", ".comp-name", 
            "a[class*='comp']", ".jd-header .company",
            ".companyInfo .companyName", ".jdHeader .companyName"
        ]
        for sel in company_selectors:
            elem = job_page.query_selector(sel)
            if elem and elem.is_visible():
                company = elem.inner_text().strip()
                break
        
        # Extract location from JD page
        location = ""
        location_selectors = [
            ".location", "[class*='location']", ".locWdth",
            ".jd-header .location", "[data-location]",
            ".companyInfo .location", ".jdHeader .location"
        ]
        for sel in location_selectors:
            elem = job_page.query_selector(sel)
            if elem and elem.is_visible():
                location = elem.inner_text().strip()
                break
        
        # Fallback: extract location from URL if page extraction failed
        if not location:
            url_lower = url.lower()
            if "bengaluru" in url_lower or "bangalore" in url_lower:
                location = "Bengaluru"
            elif "hyderabad" in url_lower or "secunderabad" in url_lower:
                location = "Hyderabad"
            elif "remote" in url_lower or "wfh" in url_lower:
                location = "Remote"
            elif "chennai" in url_lower:
                location = "Chennai"
            elif "pune" in url_lower:
                location = "Pune"
            elif "mumbai" in url_lower:
                location = "Mumbai"
            elif "delhi" in url_lower or "gurgaon" in url_lower or "noida" in url_lower:
                location = "Delhi NCR"
        
        # Extract experience from JD page
        experience = ""
        exp_selectors = [
            ".experience", "[class*='exp']", ".expwdth",
            ".jd-header .experience", ".experienceDetails"
        ]
        for sel in exp_selectors:
            elem = job_page.query_selector(sel)
            if elem and elem.is_visible():
                experience = elem.inner_text().strip()
                break
        
        # Get title from JD page (more accurate than card)
        title = ""
        title_selectors = ["h1", ".jd-header h1", "[class*='title']", ".job-title", ".jdHeader h1"]
        for sel in title_selectors:
            elem = job_page.query_selector(sel)
            if elem and elem.is_visible():
                title = elem.inner_text().strip()
                break
        
        return {
            "title": title,
            "company": company,
            "location": location,
            "experience": experience,
            "posted_date": posted,
            "jd_text": jd_text,
            "url": url,
        }

    def _record_job(self, job_data: dict, status: str, error_msg: str = None):
        """Record job to collector and update UI"""
        job_data["status"] = status
        job_data["error"] = error_msg if status not in ["applied", "chatbot", "company_site", "duplicate"] else None
        job_data["applied"] = status in ["applied", "chatbot", "company_site"]
        self.collector.add_job(job_data)
        
        # Update UI if available
        if self.ui:
            # Find the job index in collector
            job_idx = len(self.collector.jobs_data) - 1
            # Map status to JobStatus enum
            status_map = {
                "applied": JobStatus.APPLIED,
                "chatbot": JobStatus.APPLIED,
                "company_site": JobStatus.COMPANY_SITE,
                "skipped_old": JobStatus.SKIPPED_OLD,
                "skipped_irrelevant": JobStatus.SKIPPED_IRRELEVANT,
                "skipped_location": JobStatus.SKIPPED_LOCATION,
                "skipped_mismatch": JobStatus.SKIPPED_MISMATCH,
                "error": JobStatus.ERROR,
                "failed": JobStatus.ERROR,
                "duplicate": JobStatus.SKIPPED_IRRELEVANT,
            }
            ui_status = status_map.get(status, JobStatus.SKIPPED_MISMATCH)
            
            # Update the last added job row
            for row in self.ui.rows.values():
                if row.title == job_data.get("title", "") and row.company == job_data.get("company", ""):
                    row.status = ui_status
                    row.company = job_data.get("company", "")
                    row.experience = job_data.get("experience", "")
                    row.must_have_skills = job_data.get("must_have_skills", [])
                    row.good_to_have_skills = job_data.get("good_to_have_skills", [])
                    row.match_pct = job_data.get("match_percentage", 0)
                    row.missing_skills = job_data.get("missing_skills", [])
                    row.error_msg = error_msg or ""
                    if self.ui.live:
                        self.ui.live.update(self.ui._render_table())
                    break

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
            context = browser.new_context()
            context.add_cookies(cookies)
            page = context.new_page()
            
            # Move browser window off-screen if not headless and minimize_browser is True
            if not self.headless_mode and self.minimize_browser:
                try:
                    page.evaluate("() => window.moveTo(-2000, -2000)")
                    page.set_viewport_size({"width": 800, "height": 600})
                    print("  Browser window moved off-screen")
                except Exception as e:
                    print(f"  Could not move browser window: {e}")
            
            # Set longer timeout for headless mode
            page.set_default_timeout(60000)
            page.set_default_navigation_timeout(90000)

            try:
                for i, keyword in enumerate(keywords):
                    # For subsequent roles, add longer delay and ensure clean state
                    if i > 0:
                        # Longer delay between roles to prevent browser connection issues
                        page.wait_for_timeout(10000)
                        # Dismiss any overlays that may have appeared
                        self._dismiss_chatbot_overlay(page)
                        # Close any extra tabs
                        while len(context.pages) > 1:
                            try:
                                extra_page = context.pages[-1]
                                if extra_page != page:
                                    extra_page.close()
                            except Exception:
                                break
                    
                    result = self.process_role(page, keyword, max_jobs_per_role, context)
                    all_applied.extend(result["applied"])
                    all_skipped.extend(result["skipped"])
                    all_errors.extend(result["errors"])

                    if self.ui:
                        self.ui.console.print(f"\n[bold green]Role '{keyword}' complete: Applied={len(result['applied'])}, Skipped={len(result['skipped'])}, Errors={len(result['errors'])}[/bold green]")
                    else:
                        print(f"\nRole '{keyword}' complete: Applied={len(result['applied'])}, Skipped={len(result['skipped'])}, Errors={len(result['errors'])}")

                    # Small delay between roles
                    page.wait_for_timeout(3000)

            finally:
                browser.close()

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