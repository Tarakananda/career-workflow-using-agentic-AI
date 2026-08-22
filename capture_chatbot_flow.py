#!/usr/bin/env python3
"""
Test script to capture chatbot DOM during actual application flow.
"""
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright
from playwright_stealth.stealth import Stealth


def capture_chatbot_during_apply():
    with sync_playwright() as p:
        Stealth().use_sync(p)
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        
        with open('session.json') as f:
            cookies = json.load(f)
        context.add_cookies(cookies)
        
        page = context.new_page()
        
        # Go to search page
        search_url = "https://www.naukri.com/cloud--devops-engineer-jobs?experience=3"
        print(f"Navigating to search: {search_url}")
        page.goto(search_url, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_selector("[data-job-id], .jobTuple, .job-card", timeout=30000)
        page.wait_for_timeout(3000)
        
        # Get first few job cards
        cards = page.query_selector_all("[data-job-id], .jobTuple, .job-card")
        print(f"Found {len(cards)} job cards")
        
        for i, card in enumerate(cards[:5]):
            try:
                title_elem = card.query_selector("a.title, a[class*='title'], h2 a, h3 a, .job-title a")
                link_elem = card.query_selector("a[href*='job-'], a[href*='/job/'], a.title")
                
                if not title_elem or not link_elem:
                    continue
                    
                title = title_elem.inner_text().strip()
                url = link_elem.get_attribute("href")
                print(f"\n[{i+1}] {title[:60]}")
                print(f"    URL: {url}")
                
                # Click to open job detail
                job_page = None
                for attempt in range(3):
                    try:
                        with context.expect_page() as new_page_info:
                            link_elem.click()
                        job_page = new_page_info.value
                        job_page.wait_for_load_state("domcontentloaded", timeout=30000)
                        job_page.wait_for_timeout(3000)
                        break
                    except Exception as e:
                        print(f"    Failed to open (attempt {attempt+1}): {e}")
                        if job_page:
                            try: job_page.close()
                            except: pass
                        if attempt == 2:
                            job_page = None
                        time.sleep(2)
                
                if not job_page:
                    continue
                
                # Now click apply button
                print("    Looking for apply button...")
                apply_btn = job_page.query_selector("#apply-button")
                if not apply_btn or not apply_btn.is_visible():
                    # Try other selectors
                    for sel in ["button:has-text('Apply')", "button.apply-button", "[class*='apply']:not([class*='save'])", "button[id*='apply']"]:
                        apply_btn = job_page.query_selector(sel)
                        if apply_btn and apply_btn.is_visible():
                            print(f"    Found apply button with: {sel}")
                            break
                
                if apply_btn and apply_btn.is_visible():
                    print("    Clicking apply button...")
                    apply_btn.click()
                    job_page.wait_for_timeout(5000)  # Wait for chatbot to appear
                    
                    # NOW capture the chatbot DOM
                    print("    Capturing chatbot DOM...")
                    capture_chatbot_dom(job_page, i)
                    
                    job_page.close()
                    break  # Only test first job with apply button
                else:
                    print("    No apply button found")
                    job_page.close()
                    
            except Exception as e:
                print(f"    Error: {e}")
                continue
        
        input("\nPress Enter to close browser...")
        browser.close()


def capture_chatbot_dom(page, job_index):
    """Capture all visible elements that might be chatbot-related."""
    import os
    os.makedirs("txt_output", exist_ok=True)
    
    output_file = f"txt_output/chatbot_dom_job_{job_index}.txt"
    
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
    ]
    
    with open(output_file, "w") as f:
        f.write(f"=== CHATBOT DOM CAPTURE FOR JOB {job_index} ===\n")
        f.write(f"URL: {page.url}\n")
        f.write(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        for sel in chatbot_selectors:
            elems = page.query_selector_all(sel)
            visible_count = 0
            for i, el in enumerate(elems):
                try:
                    if el.is_visible():
                        visible_count += 1
                        html = el.get_attribute("outerHTML")[:3000]
                        f.write(f"\n{'='*80}\n")
                        f.write(f"SELECTOR: {sel}  INDEX: {i}  VISIBLE: {visible_count}\n")
                        f.write(f"{'='*80}\n")
                        f.write(html)
                        f.write("\n")
                except Exception as e:
                    f.write(f"Error: {e}\n")
            print(f"  {sel}: {len(elems)} total, {visible_count} visible")
        
        # Also capture full body text for question searching
        all_text = page.inner_text("body")
        f.write(f"\n{'='*80}\n")
        f.write("FULL BODY TEXT (first 10000 chars)\n")
        f.write(f"{'='*80}\n")
        f.write(all_text[:10000])
    
    print(f"    Saved to {output_file}")


if __name__ == "__main__":
    capture_chatbot_during_apply()