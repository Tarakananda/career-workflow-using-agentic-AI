#!/usr/bin/env python3
"""Main entry point for the Job Agent."""
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.search import JobSearch
from src.apply import JobApplier


def main():
    parser = argparse.ArgumentParser(description="Job Application Agent")
    parser.add_argument("--max-jobs", type=int, default=10, help="Max jobs to process")
    parser.add_argument("--threshold", type=float, default=80.0, help="Skill match threshold %")
    parser.add_argument("--max-days", type=int, default=2, help="Max days old for job posting")
    parser.add_argument("--search-only", action="store_true", help="Only search, don't apply")
    parser.add_argument("--apply-only", action="store_true", help="Only apply to previously found jobs")
    args = parser.parse_args()

    print("=" * 60)
    print("JOB AGENT - Starting")
    print("=" * 60)

    search = JobSearch()
    jobs = search.search_jobs()
    print(f"\nTotal jobs found: {len(jobs)}")

    if args.search_only:
        # Print all jobs
        for job in jobs:
            print(f"  {job['title'][:60]} | {job['company']} | {job['location']} | {job['experience']} | {job['posted_date']}")
        return

    applier = JobApplier(match_threshold=args.threshold, max_days_old=args.max_days)
    result = applier.apply_to_jobs(jobs, max_jobs=args.max_jobs)

    print("\n" + "=" * 60)
    print("FINAL SUMMARY")
    print("=" * 60)
    print(f"Applied: {len(result['applied'])}")
    for a in result['applied']:
        print(f"  ✓ {a['title'][:60]} ({a['match_pct']:.1f}%)")

    print(f"\nSkipped (low match): {len(result['skipped'])}")
    for s in result['skipped'][:10]:
        print(f"  ✗ {s['title'][:60]} ({s['match_pct']:.1f}%)")

    print(f"\nErrors: {len(result['errors'])}")
    for e in result['errors']:
        print(f"  ! {e.get('title', 'Unknown')[:60]}: {e.get('error', 'Unknown')}")


if __name__ == "__main__":
    main()