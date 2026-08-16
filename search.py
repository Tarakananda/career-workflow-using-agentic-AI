#!/usr/bin/env python3
"""Search jobs on Naukri using session and user profile."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.search import JobSearch


def main():
    search = JobSearch()
    jobs = search.search_jobs()
    print(f"\nFound {len(jobs)} jobs:")
    for job in jobs:
        print(f"  {job['title']} | {job['company']} | {job['location']} | {job['experience']} | {job['salary']}")
        print(f"    {job['url']}")


if __name__ == "__main__":
    main()