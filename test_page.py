#!/usr/bin/env python3
from pathlib import Path
import json
from playwright.sync_api import sync_playwright
from playwright_stealth.stealth import Stealth

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
        
        url = "https://www.naukri.com/aws-devops-engineer-jobs?experience=3"
        print(f"Navigating to {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=90000)
        
        # Wait for a bit
        page.wait_for_timeout(5000)
        
        # Save screenshot
        page.screenshot(path="debug_page.png")
        print("Saved screenshot to debug_page.png")
        
        # Get page title
        title = page.title()
        print(f"Page title: {title}")
        
        # Check for job cards
        cards = page.query_selector_all("[data-job-id]")
        print(f"Found {len(cards)} cards with selector [data-job-id]")
        
        # If not found, try other selectors
        if len(cards) == 0:
            cards = page.query_selector_all(".jobTuple")
            print(f"Found {len(cards)} cards with selector .jobTuple")
        
        if len(cards) == 0:
            cards = page.query_selector_all(".job-card")
            print(f"Found {len(cards)} cards with selector .job-card")
        
        # Print the page content to see what we got
        content = page.content()
        # Save to file for inspection
        with open("debug_page.html", "w", encoding="utf-8") as f:
            f.write(content)
        print("Saved page content to debug_page.html")
        
        browser.close()

if __name__ == "__main__":
    main()