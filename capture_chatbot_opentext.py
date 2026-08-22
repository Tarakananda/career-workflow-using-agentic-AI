#!/usr/bin/env python3
"""
Test script to capture chatbot DOM for a specific job known to trigger chatbot.
"""
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright
from playwright_stealth.stealth import Stealth


def capture_chatbot_for_opentext():
    with sync_playwright() as p:
        Stealth().use_sync(p)
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        
        with open('session.json') as f:
            cookies = json.load(f)
        context.add_cookies(cookies)
        
        page = context.new_page()
        
        # Go directly to the Opentext job that we know triggers chatbot
        job_url = "https://www.naukri.com/job-listings-opentext-itom-itsm-engineer-opentext-hyderabad-3-to-8-years-160726018799"
        print(f"Navigating to: {job_url}")
        page.goto(job_url, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(5000)
        
        # Click apply button
        print("Looking for apply button...")
        apply_btn = page.query_selector("#apply-button")
        if not apply_btn or not apply_btn.is_visible():
            for sel in ["button:has-text('Apply')", "button.apply-button", "[class*='apply']:not([class*='save'])", "button[id*='apply']"]:
                apply_btn = page.query_selector(sel)
                if apply_btn and apply_btn.is_visible():
                    print(f"Found apply button with: {sel}")
                    break
        
        if apply_btn and apply_btn.is_visible():
            print("Clicking apply button...")
            apply_btn.click()
            page.wait_for_timeout(8000)  # Wait longer for chatbot
            
            # Capture chatbot DOM
            print("Capturing chatbot DOM...")
            capture_chatbot_dom(page)
        else:
            print("No apply button found")
        
        browser.close()


def capture_chatbot_dom(page):
    """Capture all visible elements that might be chatbot-related."""
    import os
    os.makedirs("txt_output", exist_ok=True)
    
    output_file = "txt_output/chatbot_dom_opentext.txt"
    
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
        "[class*='radio']",
        "[class*='btn']",
        "[class*='question']",
        "[class*='field']",
    ]
    
    with open(output_file, "w") as f:
        f.write(f"=== CHATBOT DOM CAPTURE FOR OPENTEXT JOB ===\n")
        f.write(f"URL: {page.url}\n")
        f.write(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        for sel in chatbot_selectors:
            elems = page.query_selector_all(sel)
            visible_count = 0
            for i, el in enumerate(elems):
                try:
                    if el.is_visible():
                        visible_count += 1
                        html = el.get_attribute("outerHTML")[:5000]
                        f.write(f"\n{'='*80}\n")
                        f.write(f"SELECTOR: {sel}  INDEX: {i}  VISIBLE: {visible_count}\n")
                        f.write(f"{'='*80}\n")
                        f.write(html)
                        f.write("\n")
                except Exception as e:
                    f.write(f"Error: {e}\n")
            print(f"  {sel}: {len(elems)} total, {visible_count} visible")
        
        # Also capture full body text
        all_text = page.inner_text("body")
        f.write(f"\n{'='*80}\n")
        f.write("FULL BODY TEXT\n")
        f.write(f"{'='*80}\n")
        f.write(all_text)
    
    print(f"    Saved to {output_file}")


if __name__ == "__main__":
    capture_chatbot_for_opentext()