#!/usr/bin/env python3
"""
Capture detailed chatbot DOM structure from screenshots reference.
"""
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright
from playwright_stealth.stealth import Stealth


def capture_chatbot_dom_detailed():
    with sync_playwright() as p:
        Stealth().use_sync(p)
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        
        with open('session.json') as f:
            cookies = json.load(f)
        context.add_cookies(cookies)
        
        page = context.new_page()
        
        # Go to a job that triggers chatbot - use the AWS DevOps Engineer search
        search_url = "https://www.naukri.com/aws-devops-engineer-jobs?experience=3"
        print(f"Navigating to search: {search_url}")
        page.goto(search_url, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_selector("[data-job-id], .jobTuple, .job-card", timeout=30000)
        page.wait_for_timeout(3000)
        
        # Get first job card
        cards = page.query_selector_all("[data-job-id], .jobTuple, .job-card")
        print(f"Found {len(cards)} job cards")
        
        for i, card in enumerate(cards[:3]):
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
                
                # Click apply button
                print("    Looking for apply button...")
                apply_btn = job_page.query_selector("#apply-button")
                if not apply_btn or not apply_btn.is_visible():
                    for sel in ["button:has-text('Apply')", "button.apply-button", "[class*='apply']:not([class*='save'])", "button[id*='apply']"]:
                        apply_btn = job_page.query_selector(sel)
                        if apply_btn and apply_btn.is_visible():
                            print(f"    Found apply button with: {sel}")
                            break
                
                if apply_btn and apply_btn.is_visible():
                    print("    Clicking apply button...")
                    apply_btn.click()
                    job_page.wait_for_timeout(5000)
                    
                    # NOW capture the chatbot dialog in detail
                    print("    Capturing chatbot dialog DOM...")
                    capture_dialog_dom(job_page, i)
                    
                    # Don't close - let user see
                    input("    Press Enter to close this job and continue...")
                    job_page.close()
                    break  # Only test first job with chatbot
                else:
                    print("    No apply button found")
                    job_page.close()
                    
            except Exception as e:
                print(f"    Error: {e}")
                continue
        
        input("\nPress Enter to close browser...")
        browser.close()


def capture_dialog_dom(page, job_index):
    """Capture detailed DOM of the chatbot dialog."""
    import os
    os.makedirs("txt_output", exist_ok=True)
    
    output_file = f"txt_output/chatbot_dialog_detailed_job_{job_index}.txt"
    
    with open(output_file, "w") as f:
        f.write(f"=== CHATBOT DIALOG DETAILED CAPTURE - JOB {job_index} ===\n")
        f.write(f"URL: {page.url}\n")
        f.write(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        # 1. Find the dialog/modal container
        dialog_selectors = [
            "[role='dialog']",
            "[class*='dialog']",
            "[class*='modal']",
            "[class*='chatbot']",
            "[class*='sidebar']",
            "[class*='apply']",
            "aside",
            "[data-testid*='chatbot']",
            "[data-testid*='apply']",
        ]
        
        f.write("=== DIALOG CONTAINERS ===\n")
        for sel in dialog_selectors:
            elems = page.query_selector_all(sel)
            visible = [e for e in elems if e.is_visible()]
            if visible:
                f.write(f"\nSelector: {sel} - {len(visible)} visible\n")
                for i, el in enumerate(visible):
                    try:
                        html = el.get_attribute("outerHTML")[:5000]
                        f.write(f"  [{i}] HTML:\n{html}\n\n")
                    except:
                        pass
        
        # 2. Find all radio buttons with labels
        f.write("\n=== RADIO BUTTONS ===\n")
        radios = page.query_selector_all("input[type='radio']")
        for i, radio in enumerate(radios):
            try:
                if radio.is_visible():
                    radio_id = radio.get_attribute("id")
                    label_text = ""
                    if radio_id:
                        label = page.query_selector(f"label[for='{radio_id}']")
                        if label:
                            label_text = label.inner_text().strip()
                    if not label_text:
                        parent = radio.query_selector("xpath=..")
                        if parent:
                            label_text = parent.inner_text().strip()
                    f.write(f"  Radio {i}: id={radio_id}, checked={radio.is_checked()}, label='{label_text}'\n")
                    # Get full radio HTML
                    html = radio.get_attribute("outerHTML")[:2000]
                    f.write(f"    HTML: {html}\n")
            except:
                pass
        
        # 3. Find all buttons
        f.write("\n=== BUTTONS ===\n")
        buttons = page.query_selector_all("button")
        for i, btn in enumerate(buttons):
            try:
                if btn.is_visible():
                    text = btn.inner_text().strip()
                    btn_id = btn.get_attribute("id")
                    btn_class = btn.get_attribute("class")
                    disabled = btn.get_attribute("disabled")
                    aria_disabled = btn.get_attribute("aria-disabled")
                    f.write(f"  Button {i}: text='{text}', id='{btn_id}', class='{btn_class}', disabled={disabled}, aria-disabled={aria_disabled}\n")
                    html = btn.get_attribute("outerHTML")[:2000]
                    f.write(f"    HTML: {html}\n")
            except:
                pass
        
        # 4. Find text inputs
        f.write("\n=== TEXT INPUTS ===\n")
        inputs = page.query_selector_all("input[type='text'], textarea, input:not([type])")
        for i, inp in enumerate(inputs):
            try:
                if inp.is_visible():
                    inp_id = inp.get_attribute("id")
                    inp_class = inp.get_attribute("class")
                    placeholder = inp.get_attribute("placeholder")
                    value = inp.input_value()
                    f.write(f"  Input {i}: id='{inp_id}', class='{inp_class}', placeholder='{placeholder}', value='{value}'\n")
                    html = inp.get_attribute("outerHTML")[:2000]
                    f.write(f"    HTML: {html}\n")
            except:
                pass
        
        # 5. Full page text for question extraction
        f.write("\n=== FULL PAGE TEXT (first 5000 chars) ===\n")
        all_text = page.inner_text("body")
        f.write(all_text[:5000])
        
        # 6. Full page HTML for reference
        with open(f"txt_output/chatbot_page_job_{job_index}.html", "w") as html_f:
            html_f.write(page.content())
        f.write(f"\nFull HTML saved to txt_output/chatbot_page_job_{job_index}.html\n")
    
    print(f"    Detailed DOM saved to {output_file}")


if __name__ == "__main__":
    capture_chatbot_dom_detailed()