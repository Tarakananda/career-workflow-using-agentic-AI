from pathlib import Path
from typing import Any
import yaml

from playwright_stealth.stealth import Stealth
from playwright.sync_api import sync_playwright

from src.matcher import is_recent_job, should_apply, extract_skills_from_text
from src.resume import parse_resume, Resume
from src.data_collector import JobDataCollector


class JobApplier:
    def __init__(
        self,
        session_file: Path = Path("session.json"),
        profile_file: Path = Path("user_profile.yaml"),
        resume_file: Path = Path("CV_Tarakananda.pdf"),
        match_threshold: float = None,
        max_days_old: int = 2,
    ):
        self.session_file = session_file
        self.profile = yaml.safe_load(profile_file.read_text())
        self.resume: Resume = parse_resume(resume_file)

        # Use profile's apply_threshold if not explicitly provided
        if match_threshold is None:
            match_threshold = self.profile.get("apply_threshold", 0.8) * 100
        self.match_threshold = match_threshold
        self.max_days_old = max_days_old
        self.collector = JobDataCollector()

        # Build experience map from resume for answering questions
        self.experience_map = self._build_experience_map()

        # Load user profile Q&A for unknown questions
        self.profile_qa = self._load_profile_qa()

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

    def _load_profile_qa(self) -> dict[str, str]:
        """Load Q&A from user_profile.yaml for unknown questions."""
        qa = {}
        if "questions" in self.profile:
            for item in self.profile["questions"]:
                if isinstance(item, dict) and "question" in item and "answer" in item:
                    qa[item["question"].lower()] = item["answer"]
        return qa

    def _save_unknown_question(self, question: str) -> None:
        """Save unknown question to user_profile.yaml for user to answer."""
        question = question.strip()
        if not question:
            return

        # Check if already exists
        for item in self.profile.get("questions", []):
            if isinstance(item, dict) and item.get("question", "").lower() == question.lower():
                return

        if "questions" not in self.profile:
            self.profile["questions"] = []

        self.profile["questions"].append({
            "question": question,
            "answer": ""  # User needs to fill this
        })

        with open("user_profile.yaml", "w") as f:
            yaml.dump(self.profile, f, default_flow_style=False)

        print(f"  ⚠ Unknown question saved to user_profile.yaml: {question}")

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

    def _answer_application_question(self, page: Any, question: str) -> bool:
            """Try to answer an application question based on resume/profile."""
            question_lower = question.lower()

            # Check profile Q&A first
            for q, answer in self.profile_qa.items():
                if q in question_lower:
                    # Fill the answer
                    input_elem = page.query_selector("input[type='text'], textarea, input:not([type])")
                    if input_elem:
                        input_elem.fill(answer)
                        return True

            # Try to match from experience map
            for skill, exp in self.experience_map.items():
                if skill in question_lower:
                    input_elem = page.query_selector("input[type='text'], textarea, input:not([type])")
                    if input_elem:
                        input_elem.fill(exp)
                        print(f"  Answered: {question} -> {exp}")
                        return True

            # Check for common patterns
            if "notice period" in question_lower:
                notice = self.profile.get("notice_period_months", 3)
                input_elem = page.query_selector("input[type='text'], textarea, input:not([type])")
                if input_elem:
                    input_elem.fill(f"{notice} months")
                    return True

            if "current ctc" in question_lower or "expected ctc" in question_lower:
                ctc = self.profile.get("expected_ctc_lpa", self.profile.get("current_ctc_lpa", 12))
                input_elem = page.query_selector("input[type='text'], textarea, input:not([type])")
                if input_elem:
                    input_elem.fill(f"{ctc} LPA")
                    return True

            if "years of experience" in question_lower or "how many years" in question_lower:
                # Try to extract skill from question and match
                for skill, exp in self.experience_map.items():
                    if skill in question_lower:
                        input_elem = page.query_selector("input[type='text'], textarea, input:not([type])")
                        if input_elem:
                            input_elem.fill(exp)
                            print(f"  Answered: {question} -> {exp}")
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
                    answered = self._answer_application_question(page, question_text)

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
                            answered = self._answer_application_question(page, combined_text)
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

    def click_apply(self, page: Any, context: Any) -> bool:
            """Click apply button on job detail page, handle application in new tab."""
            # Wait for apply button to appear
            page.wait_for_timeout(2000)

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
                    print(f"  Found apply button with selector: {sel}")
                    try:
                        # Click with new tab handling
                        with context.expect_page() as new_page_info:
                            btn.click()
                        new_page = new_page_info.value
                        new_page.wait_for_load_state("domcontentloaded", timeout=30000)

                        # Handle application form
                        self._handle_application_form(new_page)

                        # Close the application tab and return to job detail
                        new_page.close()
                        return True
                    except Exception as e:
                        print(f"  Apply click error (new tab): {e}")
                        # Try without new tab
                        try:
                            btn.click()
                            page.wait_for_timeout(3000)
                            self._handle_application_form(page)
                            return True
                        except Exception as e2:
                            print(f"  Apply click error (same tab): {e2}")
                            continue
            print("  No apply button found with any selector")
            return False

    def sort_by_date(self, page: Any) -> None:
            """Sort search results by date."""
            try:
                print("  Waiting for sort dropdown...")
                page.wait_for_selector("#filter-sort", timeout=30000)
                sort_btn = page.query_selector("#filter-sort")
                print(f"  Sort button found: {sort_btn is not None}, visible: {sort_btn.is_visible() if sort_btn else 'N/A'}")
                if sort_btn and sort_btn.is_visible():
                    sort_btn.click()
                    print("  Sort dropdown clicked, waiting for options...")
                    page.wait_for_timeout(3000)
                    # Use text-based selector since data-id might not be on the <a>
                    date_option = page.query_selector("[data-filter-id='sort'] a:has-text('Date'), [data-filter-id='sort'] li:has-text('Date')")
                    print(f"  Date option (primary): {date_option is not None}")
                    if not date_option:
                        date_option = page.query_selector("a[data-id='filter-sort-f']")
                        print(f"  Date option (data-id): {date_option is not None}")
                    if not date_option:
                        # Try finding by text in any element within the dropdown
                        date_option = page.query_selector("[data-filter-id='sort'] *:has-text('Date')")
                        print(f"  Date option (text search): {date_option is not None}")
                    if date_option and date_option.is_visible():
                        print("  Clicking date option...")
                        date_option.click()
                        page.wait_for_selector("[data-job-id], .jobTuple, .job-card", timeout=30000)
                        print("  Sorted by date")
                    else:
                        print("  Date option not found or not visible")
                else:
                    print("  Sort button not found or not visible")
            except Exception as e:
                print(f"  Sort by date failed: {e}")

    def _apply_location_filters(self, page: Any) -> None:
            """Apply location filters from user profile."""
            locations = self.profile.get("preferred_locations", [])
            if not locations:
                return

            try:
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
                                loc_elem.click()
                                page.wait_for_timeout(500)

                        apply_btn = page.query_selector("button:has-text('Apply'), button:has-text('Done')")
                        if apply_btn:
                            apply_btn.click()
                            page.wait_for_load_state("networkidle", timeout=20000)
                            page.wait_for_timeout(3000)
            except Exception as e:
                print(f"  Location filter skipped: {e}")

    def process_role(self, page: Any, keyword: str, max_jobs: int, context: Any) -> dict:
            """Process a single role: search, filter, check each job, apply if match."""
            base_url = f"https://www.naukri.com/{keyword.lower().replace(' ', '-').replace('&', '')}-jobs"
            search_url = f"{base_url}?experience=3"
            print(f"\n{'='*60}")
            print(f"Processing role: {keyword}")
            print(f"URL: {search_url}")
            print(f"{'='*60}")

            applied = []
            skipped = []
            errors = []
            processed = 0
            card_index = 0

            while processed < max_jobs:
                # Reload to avoid cache and get fresh cards
                page.goto(search_url, wait_until="domcontentloaded", timeout=90000)
                page.wait_for_selector("[data-job-id], .jobTuple, .job-card", timeout=30000)

                # Apply location filters (disabled for now - can be enabled later)
                # Sort by date on EVERY reload since page navigation resets sort
                self.sort_by_date(page)

                # Get fresh job cards
                cards = page.query_selector_all("[data-job-id], .jobTuple, .job-card")
                print(f"Found {len(cards)} job cards")

                if card_index >= len(cards):
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
                        print(f"  [{card_index+1}] Skip (old): {title[:50]} | Posted: {posted}")
                        card_index += 1
                        continue

                    # Check if relevant title
                    if not self.is_relevant_title(title):
                        print(f"  [{card_index+1}] Skip (irrelevant): {title[:50]} | Posted: {posted}")
                        card_index += 1
                        continue

                    print(f"\n  [{card_index+1}] Checking: {title[:60]}")
                    print(f"      Posted: {posted}")
                    print(f"      Company: {company}")
                    print(f"      Experience: {experience}")
                    print(f"      URL: {url}")

                    # Click job to open detail page
                    try:
                        link_elem.click()
                        page.wait_for_load_state("domcontentloaded", timeout=30000)
                        page.wait_for_selector("[class*='jd-container'], .job-desc, .JDContent", timeout=30000)
                    except Exception as e:
                        print(f"      ✗ Failed to open job: {e}")
                        errors.append({"title": title, "url": url, "error": str(e)})
                        card_index += 1
                        continue

                    # Extract JD and check skills
                    try:
                        jd_text = self.extract_job_description(page)
                        jd_text = jd_text[:5000]

                        job_skills = extract_skills_from_text(jd_text)
                        should, match_pct, matched, missing = should_apply(
                            self.resume.skills, jd_text, self.match_threshold
                        )

                        print(f"      Skills in JD: {job_skills[:10]}")
                        print(f"      Match: {match_pct:.1f}% | Matched: {matched} | Missing: {missing[:5]}")

                        # Collect job data for output file
                        job_data = {
                            "role": keyword,
                            "title": title,
                            "company": company,
                            "experience": experience,
                            "posted_date": posted,
                            "url": url,
                            "jd_text": jd_text,
                            "jd_skills": job_skills,
                            "resume_skills": self.resume.skills,
                            "matched_skills": matched,
                            "missing_skills": missing,
                            "match_percentage": round(match_pct, 1),
                            "applied": False,
                            "status": "skipped" if not should else "applied",
                            "error": None
    }

                        if should:
                            print(f"      ✓ Match > {self.match_threshold}%, applying...")
                            # Wait for apply button to be ready - use loop with query_selector
                            apply_btn = None
                            for attempt in range(15):
                                page.wait_for_timeout(1000)
                                apply_btn = page.query_selector("#apply-button")
                                if apply_btn:
                                    print(f"  Attempt {attempt+1}: Apply button found via query_selector, is_visible={apply_btn.is_visible()}, url={page.url}")
                                    break
                                else:
                                    print(f"  Attempt {attempt+1}: Apply button not found yet, url={page.url}")

                            if not apply_btn:
                                print("  Apply button not found after 15 seconds")
                                # Debug: dump all visible buttons
                                buttons = page.query_selector_all("button")
                                for b in buttons:
                                    if b.is_visible():
                                        txt = b.inner_text().strip().lower()
                                        if 'apply' in txt or 'company' in txt or 'save' in txt:
                                            print(f"  Visible button: '{b.inner_text().strip()}' ID: {b.get_attribute('id')} Class: {b.get_attribute('class')}")

                            if self.click_apply(page, context):
                                page.wait_for_timeout(3000)
                                applied.append({
                                    "title": title,
                                    "url": url,
                                    "match_pct": match_pct,
                                    "posted": posted
                                })
                                job_data["applied"] = True
                                job_data["status"] = "applied"
                                print(f"      ✓ Applied successfully")
                            else:
                                errors.append({
                                    "title": title,
                                    "url": url,
                                    "error": "Apply button not found"
                                })
                                job_data["status"] = "error"
                                job_data["error"] = "Apply button not found"
                                print(f"      ✗ Apply button not found")
                        else:
                            skipped.append({
                                "title": title,
                                "url": url,
                                "match_pct": match_pct,
                                "missing": missing,
                                "posted": posted
                            })
                            print(f"      ✗ Match < {self.match_threshold}%, skipping")

                        self.collector.add_job(job_data)
                        processed += 1

                    except Exception as e:
                        print(f"      ✗ Error processing JD: {e}")
                        errors.append({"title": title, "url": url, "error": str(e)})
                        job_data["status"] = "error"
                        job_data["error"] = str(e)
                        self.collector.add_job(job_data)

                    # Move to next card (will reload page)
                    card_index += 1

                except Exception as e:
                    print(f"  ✗ Error with card {card_index}: {e}")
                    card_index += 1
                    continue

            return {"applied": applied, "skipped": skipped, "errors": errors}

    def run(self, max_jobs_per_role: int = 5) -> dict:
            """Run the full pipeline: process each role sequentially."""
            cookies = self.load_session()
            if not cookies:
                raise RuntimeError("No valid session. Run login.py first.")

            keywords = self.profile.get("strict_roles", [])

            all_applied = []
            all_skipped = []
            all_errors = []

            with sync_playwright() as p:
                Stealth().use_sync(p)
                browser = p.chromium.launch(headless=False)
                context = browser.new_context()
                context.add_cookies(cookies)
                page = context.new_page()

                try:
                    for keyword in keywords:
                        result = self.process_role(page, keyword, max_jobs_per_role, context)
                        all_applied.extend(result["applied"])
                        all_skipped.extend(result["skipped"])
                        all_errors.extend(result["errors"])

                        print(f"\nRole '{keyword}' complete: Applied={len(result['applied'])}, Skipped={len(result['skipped'])}, Errors={len(result['errors'])}")

                        # Small delay between roles
                        page.wait_for_timeout(2000)

                finally:
                    browser.close()

            # Print table and save file
            self.collector.print_table()
            filepath = self.collector.save()

            return {
                "applied": all_applied,
                "skipped": all_skipped,
                "errors": all_errors,
                "output_file": str(filepath)
            }


def main():
    from src.search import JobSearch

    applier = JobApplier()
    result = applier.run(max_jobs_per_role=5)

    print("\n" + "=" * 60)
    print("FINAL SUMMARY")
    print("=" * 60)
    print(f"Applied: {len(result['applied'])}")
    for a in result['applied']:
        print(f"  ✓ {a['title'][:60]} ({a['match_pct']:.1f}%) | Posted: {a.get('posted', 'Unknown')}")

    print(f"\nSkipped (low match): {len(result['skipped'])}")
    for s in result['skipped'][:10]:
        print(f"  ✗ {s['title'][:60]} ({s['match_pct']:.1f}%) | Posted: {s.get('posted', 'Unknown')}")

    print(f"\nErrors: {len(result['errors'])}")
    for e in result['errors']:
        print(f"  ! {e.get('title', 'Unknown')[:60]}: {e.get('error', 'Unknown')}")

    print(f"\nOutput saved to: {result.get('output_file', 'N/A')}")


if __name__ == "__main__":
    main()
