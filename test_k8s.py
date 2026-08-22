#!/usr/bin/env python3
from pathlib import Path
import json
from playwright.sync_api import sync_playwright
from playwright_stealth.stealth import Stealth
from src.search import JobSearch

def main():
    session_file = Path("session.json")
    if not session_file.exists():
        print("No session file")
        return

    with open(session_file, encoding="utf-8") as fh:
        cookies = json.load(fh)

    with sync_playwright() as p:
        Stealth().use_sync(p)
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        context.add_cookies(cookies)
        page = context.new_page()
        
        keyword = "Kubernetes Administrator"
        salary_min = 0
        salary_max = 5000000
        job_types = []
        
        print(f"Searching for: {keyword}")
        try:
            # We'll create an instance of JobSearch to use its method
            search = JobSearch()
            jobs = search._search_keyword(page, keyword, salary_min, salary_max, job_types)
            print(f"Found {len(jobs)} jobs")
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            page.close()
            context.close()
            browser.close()

if __name__ == "__main__":
    main()