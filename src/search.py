from pathlib import Path
from typing import Any
import yaml
from playwright.async_api import async_playwright
from playwright_stealth import Stealth


class JobSearch:
    def __init__(self, session_file: Path = Path("session.json"), profile_file: Path = Path("user_profile.yaml")):
        self.session_file = session_file
        self.profile = yaml.safe_load(profile_file.read_text())

    async def load_session(self) -> list[dict[str, Any]] | None:
        if not self.session_file.exists():
            return None
        import json
        with open(self.session_file, encoding="utf-8") as fh:
            cookies = json.load(fh)
        return cookies if isinstance(cookies, list) and len(cookies) > 0 else None

    async def search_jobs(self) -> list[dict[str, Any]]:
        cookies = await self.load_session()
        if not cookies:
            raise RuntimeError("No valid session. Run login.py first.")

        all_jobs = []
        keywords = self.profile.get("strict_roles", [])
        salary_min = self.profile.get("salary_min", 0)
        salary_max = self.profile.get("salary_max", 5000000)
        job_types = self.profile.get("job_types", [])

        for keyword in keywords:
            async with Stealth().use_async(async_playwright()) as p:
                browser = await p.chromium.launch(headless=False)
                context = await browser.new_context()
                await context.add_cookies(cookies)
                page = await context.new_page()
                try:
                    print(f"Searching for: {keyword}")
                    jobs = await self._search_keyword(page, keyword, salary_min, salary_max, job_types)
                    all_jobs.extend(jobs)
                finally:
                    await page.close()
                    await context.close()
                    await browser.close()

        return all_jobs

    async def _search_keyword(self, page: Any, keyword: str, salary_min: int, salary_max: int, job_types: list[str]) -> list[dict[str, Any]]:
        base_url = f"https://www.naukri.com/{keyword.lower().replace(' ', '-').replace('&', '')}-jobs"
        search_url = f"{base_url}?experience=3"
        print(f"  Navigating to: {search_url}")
        await page.goto(search_url, wait_until="domcontentloaded", timeout=90000)
        await page.wait_for_timeout(5000)
        # Don't wait for networkidle - just wait for job cards to appear
        await page.wait_for_selector("[data-job-id], .jobTuple, .job-card", timeout=60000)

        await self._apply_filters(page, salary_min, salary_max, job_types)

        # Ensure sort by date is applied after each page navigation
        await self._sort_by_date(page)

        jobs = []
        jobs.extend(await self._extract_jobs(page))
        return jobs

    async def _sort_by_date(self, page: Any) -> None:
        max_retries = 2
        for attempt in range(max_retries):
            try:
                await page.wait_for_selector("#filter-sort", timeout=20000)
                sort_btn = await page.query_selector("#filter-sort")
                if sort_btn and await sort_btn.is_visible():
                    await sort_btn.click()
                    await page.wait_for_timeout(2000)
                    date_option = await page.query_selector("[data-filter-id='sort'] a[data-id='filter-sort-f']")
                    if date_option and await date_option.is_visible():
                        await date_option.click()
                        await page.wait_for_selector("[data-job-id], .jobTuple, .job-card", timeout=20000)
                        print("  Sorted by date")
                        return
                    else:
                        print("  Date option not found")
                else:
                    print("  Sort button not found")
            except Exception as e:
                print(f"  Sort by date attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    await page.wait_for_timeout(2000)
        print("  Sort by date failed after retries")

    async def _apply_filters(self, page: Any, salary_min: int, salary_max: int, job_types: list[str]) -> None:
        # Don't apply work mode filter - leave it blank as requested
        # Only apply salary filter if needed
        try:
            salary_btn = await page.query_selector("button:has-text('Salary'), span:has-text('Salary')")
            if salary_btn and await salary_btn.is_visible():
                await salary_btn.click()
                await page.wait_for_timeout(1000)
                min_input = await page.query_selector("input[placeholder*='Min'], input[name*='min' i]")
                max_input = await page.query_selector("input[placeholder*='Max'], input[name*='max' i]")
                if min_input:
                    await min_input.fill(str(salary_min // 100000))
                if max_input:
                    await max_input.fill(str(salary_max // 100000))
                apply_btn = await page.query_selector("button:has-text('Apply'), button:has-text('Done')")
                if apply_btn:
                    await apply_btn.click()
                    await page.wait_for_load_state("networkidle", timeout=10000)
        except Exception as e:
            print(f"Salary filter failed: {e}")

        # Skip job type filter (work mode) - leave it blank

    async def _extract_jobs(self, page: Any) -> list[dict[str, Any]]:
        jobs = []
        await page.wait_for_timeout(3000)

        json_ld = await page.query_selector("script[type='application/ld+json']")
        if json_ld:
            import json
            try:
                data = json.loads(await json_ld.inner_text())
                if isinstance(data, dict) and data.get("@type") == "ItemList":
                    for item in data.get("itemListElement", []):
                        job_data = item.get("item", {})
                        jobs.append({
                            "title": job_data.get("name", ""),
                            "company": "",
                            "location": "",
                            "experience": "",
                            "salary": "",
                            "url": job_data.get("url", ""),
                            "posted_date": "",
                        })
                    print(f"  Extracted {len(jobs)} jobs from JSON-LD")
                    return jobs
            except Exception as e:
                print(f"  JSON-LD parse error: {e}")

        selectors = [
            "[data-job-id]",
            ".jobTuple",
            ".job-card",
            "article.jobTuple",
            ".list article",
            ".srp-jobtuple-wrapper",
        ]

        cards = []
        for sel in selectors:
            cards = await page.query_selector_all(sel)
            if cards:
                print(f"  Found {len(cards)} cards with selector: {sel}")
                break

        if not cards:
            print("  No job cards found")
            return []

        for card in cards:
            try:
                title_elem = await card.query_selector("a.title, a[class*='title'], h2 a, h3 a, .job-title a")
                company_elem = await card.query_selector("a.company, a[class*='company'], .companyName, .subTitle")
                location_elem = await card.query_selector(".location, [class*='location'], .locWdth, .location-span")
                exp_elem = await card.query_selector(".exp, [class*='exp'], .experience, .expwdth")
                salary_elem = await card.query_selector(".salary, [class*='salary'], .sal, .salary-span")
                link_elem = await card.query_selector("a[href*='job-'], a[href*='/job/'], a.title")
                posted_elem = await card.query_selector(".job-post-day, [class*='post-day'], [class*='posted']")

                if title_elem:
                    jobs.append({
                        "title": (await title_elem.inner_text()).strip(),
                        "company": (await company_elem.inner_text()).strip() if company_elem else "",
                        "location": (await location_elem.inner_text()).strip() if location_elem else "",
                        "experience": (await exp_elem.inner_text()).strip() if exp_elem else "",
                        "salary": (await salary_elem.inner_text()).strip() if salary_elem else "",
                        "url": await link_elem.get_attribute("href") if link_elem else "",
                        "posted_date": (await posted_elem.inner_text()).strip() if posted_elem else "",
                    })
            except Exception as e:
                print(f"  Error extracting job: {e}")
                continue
        return jobs


async def main():
    search = JobSearch()
    jobs = await search.search_jobs()
    print(f"\nFound {len(jobs)} jobs:")
    for job in jobs[:10]:
        print(f"  {job['title']} | {job['company']} | {job['location']} | {job['experience']} | {job['salary']}")
        print(f"    {job['url']}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())