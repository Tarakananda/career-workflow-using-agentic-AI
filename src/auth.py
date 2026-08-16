from pathlib import Path
from typing import Any
from playwright.sync_api import sync_playwright
from playwright_stealth.stealth import Stealth


class NaukriAuth:
    def __init__(self, email: str, password: str, session_file: Path = Path("session.json")):
        self.email = email
        self.password = password
        self.session_file = session_file

    def login(self) -> bool:
        if self.is_authenticated():
            print("Session is already valid")
            return True

        print("No valid session found, starting login flow")
        with sync_playwright() as p:
            Stealth().use_sync(p)
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            try:
                self._perform_login(page)
                cookies = context.cookies()
                self.save_session(cookies)
                print("Naukri authentication successful")
                return True
            except Exception as exc:
                print(f"Authentication failed: {exc}")
                return False
            finally:
                browser.close()

    def is_authenticated(self) -> bool:
        if not self.session_file.exists():
            return False
        cookies = self.load_session()
        if not cookies:
            return False
        print("Valid session found, verifying...")
        with sync_playwright() as p:
            Stealth().use_sync(p)
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            context.add_cookies(cookies)
            page = context.new_page()
            try:
                page.goto("https://www.naukri.com", wait_until="networkidle", timeout=30000)
                page.wait_for_load_state("networkidle", timeout=15000)
                account_menu = page.query_selector(
                    "a[href*='account'], .user-profile, [data-testid='user-menu']"
                )
                if account_menu is not None:
                    print("Session is valid")
                    return True
                print("Session is invalid")
                return False
            except Exception as exc:
                print(f"Session validation error: {exc}")
                return False
            finally:
                browser.close()

    def save_session(self, cookies: list[dict[str, Any]]) -> None:
        self.session_file.parent.mkdir(parents=True, exist_ok=True)
        import json
        with open(self.session_file, "w", encoding="utf-8") as fh:
            json.dump(cookies, fh, indent=2, ensure_ascii=False)
        print(f"Session saved to {self.session_file}")

    def load_session(self) -> list[dict[str, Any]] | None:
        if not self.session_file.exists():
            return None
        try:
            import json
            with open(self.session_file, encoding="utf-8") as fh:
                cookies = json.load(fh)
            if isinstance(cookies, list) and len(cookies) > 0:
                return cookies
            return None
        except (json.JSONDecodeError, OSError) as exc:
            print(f"Failed to load session: {exc}")
            return None

    def _perform_login(self, page: Any) -> None:
        page.goto("https://www.naukri.com/nlogin/login", wait_until="networkidle", timeout=30000)
        page.wait_for_load_state("networkidle", timeout=15000)
        
        email_selector = "input[type='email'], input[name='email'], input[placeholder*='email' i]"
        page.wait_for_selector(email_selector, timeout=10000)
        page.fill(email_selector, self.email)
        
        password_selector = "input[type='password'], input[name='password']"
        page.fill(password_selector, self.password)
        
        submit_btn = page.query_selector("button[type='submit'], button:has-text('Login')")
        if submit_btn is not None:
            submit_btn.click()
        else:
            page.click("text=Login", timeout=10000)
        
        page.wait_for_load_state("networkidle", timeout=30000)
        page.wait_for_url("**/mnjuser/**", timeout=30000)
        print("Login form submitted")