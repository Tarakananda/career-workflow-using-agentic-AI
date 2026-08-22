with open('src/apply_new.py', 'r') as f:
    content = f.read()

old_save = '''    def _click_chatbot_save(self, chatbot, page: Any = None) -> bool:
        """Click Save button in chatbot dialog. Searches both chatbot container and full page."""
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
        return False'''

new_save = '''    def _click_chatbot_save(self, chatbot, page: Any = None) -> bool:
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
        return False"""

with open('src/apply_new.py', 'r') as f:
    content = f.read()

old = '''    def _click_chatbot_save(self, chatbot, page: Any = None) -> bool:
        """Click Save button in chatbot dialog. Searches both chatbot container and full page."""
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
        return False'''

if old_save in content:
    content = content.replace(old_save, new_save)
    print("Replaced _click_chatbot_save method")
else:
    print("Could not find _click_chatbot_save method to replace")

with open('src/apply_new.py', 'w') as f:
    f.write(content)
EOF