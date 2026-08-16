from pathlib import Path
from typing import Any
import yaml
from playwright.sync_api import sync_playwright
from playwright_stealth.stealth import Stealth

from src.matcher import is_recent_job, should_apply, extract_skills_from_text
from src.resume import parse_resume, Resume


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

    def load_session(self) -> list[dict[str, Any]] | None:
        if not self.session_file.exists():
            return None
        import json
        with open(self.session_file, encoding="utf-8") as fh:
            cookies = json.load(fh)
        return cookies if isinstance(cookies, list) and len(cookies) > 0 else None

    def get_recent_jobs(self, jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Filter jobs posted within max_days_old."""
        recent = []
        for job in jobs:
            posted = job.get("posted_date", "")
            if is_recent_job(posted, self.max_days_old):
                recent.append(job)
                print(f"  Recent: {job['title'][:50]} | Posted: {posted}")
            else:
                print(f"  Skip (old): {job['title'][:50]} | Posted: {posted}")
        return recent

    def extract_job_description(self, page: Any) -> str:
        """Extract full job description from job detail page."""
        # Wait for job description to load
        page.wait_for_timeout(2000)
        
        # More specific selectors for Naukri job description
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
                if len(text) > 100:  # Ensure we got substantial content
                    return text
        
        # Fallback: try to get text from the main job detail container
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

    def apply_to_jobs(self, jobs: list[dict[str, Any]], max_jobs: int = 10) -> dict:
        """Apply to matching recent jobs."""
        cookies = self.load_session()
        if not cookies:
            raise RuntimeError("No valid session. Run login.py first.")

        recent_jobs = self.get_recent_jobs(jobs)
        print(f"\nFound {len(recent_jobs)} recent jobs (within {self.max_days_old} days)")

        # Pre-filter: only consider DevOps/Cloud/SRE relevant titles
        relevant_keywords = ["devops", "cloud", "sre", "site reliability", "aws", "azure", "gcp", 
                            "kubernetes", "k8s", "docker", "terraform", "ansible", "jenkins",
                            "ci/cd", "infrastructure", "platform", "reliability", "observability",
                            "prometheus", "grafana", "monitoring", "logging", "automation"]
        
        # Exclude patterns (developer roles that aren't DevOps)
        exclude_patterns = [
            "java developer", "python developer", "full stack", ".net", "dot net",
            "react", "node js", "nodejs", "angular", "vue", "frontend", "backend",
            "salesforce", "sap", "scrum master", "business analyst", "data scientist",
            "data engineer", "ml engineer", "ai engineer", "mlops", "genai", "llm",
            "network engineer", "security engineer", "support engineer", "qa engineer",
            "test engineer", "quality assurance", "php", "laravel", "wordpress",
        ]
        
        # Deduplicate by URL
        seen_urls = set()
        filtered_jobs = []
        for job in recent_jobs:
            url = job.get('url', '')
            if url in seen_urls:
                continue
            seen_urls.add(url)
            
            title_lower = job['title'].lower()
            
            # Check exclude patterns first
            if any(ex in title_lower for ex in exclude_patterns):
                print(f"  Skip (excluded): {job['title'][:60]}")
                continue
            
            # Check relevant keywords
            if any(kw in title_lower for kw in relevant_keywords):
                filtered_jobs.append(job)
            else:
                print(f"  Skip (irrelevant title): {job['title'][:60]}")
        
        print(f"After title filter: {len(filtered_jobs)} relevant jobs")
        
        # Limit for testing
        filtered_jobs = filtered_jobs[:max_jobs]
        print(f"Processing first {len(filtered_jobs)} jobs...")

        applied = []
        skipped = []
        errors = []

        with sync_playwright() as p:
            Stealth().use_sync(p)
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            context.add_cookies(cookies)

            for job in filtered_jobs:
                page = context.new_page()
                try:
                    print(f"\nProcessing: {job['title'][:60]} at {job['company']}")
                    page.goto(job["url"], wait_until="domcontentloaded", timeout=90000)
                    # Wait for job description container
                    page.wait_for_selector("[class*='jd-container'], .job-desc, .JDContent", timeout=30000)

                    jd_text = self.extract_job_description(page)
                    
                    # Only use first 5000 chars to avoid noise
                    jd_text = jd_text[:5000]
                    
                    job_skills = extract_skills_from_text(jd_text)
                    
                    should, match_pct, matched, missing = should_apply(
                        self.resume.skills, jd_text, self.match_threshold
                    )
                    
                    print(f"  Skills found in JD: {job_skills[:15]}")
                    print(f"  Resume skills: {self.resume.skills[:15]}")
                    print(f"  Match: {match_pct:.1f}% | Matched: {matched} | Missing: {missing[:10]}")

                    if should:
                        print(f"  ✓ Match > {self.match_threshold}%, applying...")
                        if self.click_apply(page):
                            page.wait_for_timeout(3000)
                            applied.append({**job, "match_pct": match_pct})
                            print(f"  ✓ Applied successfully")
                        else:
                            errors.append({**job, "error": "Apply button not found"})
                            print(f"  ✗ Apply button not found")
                    else:
                        skipped.append({**job, "match_pct": match_pct, "missing": missing})
                        print(f"  ✗ Match < {self.match_threshold}%, skipping")

                except Exception as e:
                    errors.append({**job, "error": str(e)})
                    print(f"  ✗ Error: {e}")
                finally:
                    page.close()

            browser.close()

        return {
            "applied": applied,
            "skipped": skipped,
            "errors": errors,
        }


def main():
    from src.search import JobSearch
    
    search = JobSearch()
    jobs = search.search_jobs()
    
    applier = JobApplier()
    result = applier.apply_to_jobs(jobs)
    
    print("\n=== SUMMARY ===")
    print(f"Applied: {len(result['applied'])}")
    for a in result['applied']:
        print(f"  - {a['title'][:50]} ({a['match_pct']:.1f}%)")
    
    print(f"\nSkipped (low match): {len(result['skipped'])}")
    for s in result['skipped']:
        print(f"  - {s['title'][:50]} ({s['match_pct']:.1f}%)")
    
    print(f"\nErrors: {len(result['errors'])}")
    for e in result['errors']:
        print(f"  - {e.get('title', 'Unknown')[:50]}: {e.get('error', 'Unknown')}")


if __name__ == "__main__":
    main()