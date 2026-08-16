from pathlib import Path
from typing import Any
import yaml
from playwright.sync_api import sync_playwright
from playwright_stealth.stealth import Stealth

from src.matcher import is_recent_job, should_apply, extract_skills_from_text
from src.resume import parse_resume, Resume
from src.data_collector import JobDataCollector


class JobApplier:
    def __init__(
        self,
        session_file: Path = Path("session.json"),
        profile_file: Path = Path("user_profile.yaml"),
        resume_file: Path = Path("CV_Tarakananda.pdf"),
        match_threshold: float = 80.0,
        max_days_old: int = 2,
    ):
        self.session_file = session_file
        self.profile = yaml.safe_load(profile_file.read_text())
        self.resume: Resume = parse_resume(resume_file)
        self.match_threshold = match_threshold
        self.max_days_old = max_days_old
        self.collector = JobDataCollector()

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

    def click_apply(self, page: Any) -> bool:
        """Click apply button on job detail page."""
        apply_selectors = [
            "button:has-text('Apply')",
            "a:has-text('Apply')",
            "[class*='apply']:not([class*='save'])",
            "button[id*='apply']",
            "a[id*='apply']",
            ".apply-button",
            "#apply-button",
        ]
        
        for sel in apply_selectors:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                try:
                    btn.click()
                    return True
                except Exception:
                    continue
        return False

    def get_posted_date_from_card(self, card: Any) -> str:
        """Extract posted date from job card on search results page."""
        posted_elem = card.query_selector(".job-post-day, [class*='post-day'], [class*='posted']")
        if posted_elem:
            return posted_elem.inner_text().strip()
        return ""

    def get_company_from_card(self, card: Any) -> str:
        """Extract company name from job card."""
        company_elem = card.query_selector("a.company, a[class*='company'], .companyName, .subTitle")
        if company_elem:
            return company_elem.inner_text().strip()
        return ""

    def get_experience_from_card(self, card: Any) -> str:
        """Extract experience from job card."""
        exp_elem = card.query_selector(".exp, [class*='exp'], .experience, .expwdth")
        if exp_elem:
            return exp_elem.inner_text().strip()
        return ""

    def is_relevant_title(self, title: str) -> bool:
        """Check if job title is relevant (DevOps/Cloud/SRE)."""
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

    def process_role(self, page: Any, keyword: str, max_jobs: int) -> dict:
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
            
            # Sort by date (only on first iteration)
            if card_index == 0:
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
                        if self.click_apply(page):
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

    def sort_by_date(self, page: Any) -> None:
        """Sort search results by date."""
        try:
            page.wait_for_selector("#filter-sort", timeout=20000)
            sort_btn = page.query_selector("#filter-sort")
            if sort_btn and sort_btn.is_visible():
                sort_btn.click()
                page.wait_for_timeout(2000)
                date_option = page.query_selector("[data-filter-id='sort'] a[data-id='filter-sort-f']")
                if date_option and date_option.is_visible():
                    date_option.click()
                    page.wait_for_selector("[data-job-id], .jobTuple, .job-card", timeout=20000)
                    print("  Sorted by date")
                else:
                    print("  Date option not found")
            else:
                print("  Sort button not found")
        except Exception as e:
            print(f"  Sort by date failed: {e}")

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
                    result = self.process_role(page, keyword, max_jobs_per_role)
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