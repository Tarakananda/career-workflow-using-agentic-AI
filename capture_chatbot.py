#!/usr/bin/env python3
"""
Test script to capture chatbot DOM structure on Naukri.
Run this after login to see the actual chatbot HTML.
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from playwright_stealth.stealth import Stealth


def capture_chatbot_dom():
    with sync_playwright() as p:
        Stealth().use_sync(p)
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        
        with open('session.json') as f:
            cookies = json.load(f)
        context.add_cookies(cookies)
        
        page = context.new_page()
        
        # Go to a job that has chatbot apply
        # Using a known job URL that triggers chatbot
        job_url = "https://www.naukri.com/job-listings-opentext-itom-itsm-engineer-opentext-hyderabad-3-to-8-years-160726018799"
        print(f"Navigating to: {job_url}")
        page.goto(job_url, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(5000)
        
        # Click apply button to trigger chatbot
        apply_btn = page.query_selector("#apply-button")
        if apply_btn and apply_btn.is_visible():
            print("Clicking apply button...")
            apply_btn.click()
            page.wait_for_timeout(5000)
        
        # Now capture all visible elements that might be chatbot
        print("\n=== CAPTURING CHATBOT DOM ===\n")
        
        # Get all visible elements with common chatbot-related classes
        chatbot_selectors = [
            "[class*='chatbot']",
            "[class*='sidebar']", 
            "[class*='apply']",
            "aside",
            "[role='dialog']",
            "[class*='panel']",
            "[class*='drawer']",
            "[class*='question']",
            "[class*='form']",
            "[data-testid*='apply']",
            "[class*='overlay']",
            "button",
            "input",
            "textarea",
            "select",
            "label",
        ]
        
        import os
        os.makedirs("txt_output", exist_ok=True)
        
        with open("txt_output/chatbot_dom_capture.txt", "w") as f:
            for sel in chatbot_selectors:
                elems = page.query_selector_all(sel)
                visible_count = 0
                for i, el in enumerate(elems):
                    try:
                        if el.is_visible():
                            visible_count += 1
                            html = el.get_attribute("outerHTML")[:2000]
                            f.write(f"\n{'='*80}\n")
                            f.write(f"SELECTOR: {sel}  INDEX: {i}  VISIBLE: {visible_count}\n")
                            f.write(f"{'='*80}\n")
                            f.write(html)
                            f.write("\n")
                    except Exception as e:
                        pass
                print(f"  {sel}: {len(elems)} total, {visible_count} visible")
        
        # Also capture full body HTML for reference
        body_html = page.content()
        with open("txt_output/full_page.html", "w") as f:
            f.write(body_html)
        print("\nFull page HTML saved to txt_output/full_page.html")
        
        # Try to find the question text
        print("\n=== SEARCHING FOR QUESTION TEXT ===")
        all_text = page.inner_text("body")
        lines = all_text.split('\n')
        for line in lines:
            line = line.strip()
            if any(kw in line.lower() for kw in ['open text', 'bridge manager', 'operations bridge', 'years of experience', 'how many years']):
                print(f"  FOUND: {line[:200]}")
        
        # Wait for user to inspect
        input("\nPress Enter to close browser...")
        browser.close()


if __name__ == "__main__":
    capture_chatbot_dom()