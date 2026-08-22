#!/usr/bin/env python3
"""Main entry point for the Job Agent."""
import sys
import argparse
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.search import JobSearch
from src.apply_new import JobApplier
from src.ui import create_ui


async def main():
    parser = argparse.ArgumentParser(description="Job Application Agent")
    parser.add_argument("--max-jobs", type=int, default=5, help="Max jobs per role to process")
    parser.add_argument("--threshold", type=float, default=80.0, help="Skill match threshold %%")
    parser.add_argument("--max-days", type=int, default=1, help="Max days old for job posting")
    parser.add_argument("--search-only", action="store_true", help="Only search, don't apply")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be applied without applying")
    parser.add_argument("--parallel", type=int, default=3, help="Max parallel jobs (default: 3)")
    parser.add_argument("--no-ui", action="store_true", help="Disable live UI, use simple output")
    args = parser.parse_args()

    print("=" * 60)
    print("JOB AGENT - Starting")
    print("=" * 60)

    if args.search_only:
        search = JobSearch()
        jobs = await search.search_jobs()
        print(f"\nTotal jobs found: {len(jobs)}")
        for job in jobs:
            print(f"  {job['title'][:60]} | {job['company']} | {job['location']} | {job['experience']} | {job['posted_date']}")
        return

    ui = None if args.no_ui else create_ui()
    applier = JobApplier(match_threshold=args.threshold, max_days_old=args.max_days, ui=ui, max_parallel=args.parallel)
    
    if args.dry_run:
        print("\n[DRY RUN] Use --search-only to see jobs, or run without --dry-run to apply.")
        print("This version processes one role at a time, checking each job on the page.")
        return

    result = await applier.run(max_jobs_per_role=args.max_jobs)

    # Final summary is handled by UI if enabled
    if args.no_ui:
        print("\n" + "=" * 60)
        print("FINAL SUMMARY")
        print("=" * 60)
        print(f"Applied: {len(result['applied'])}")
        for a in result['applied']:
            print(f"  ✓ {a['title'][:60]} ({a['match_pct']:.1f}%) | Posted: {a.get('posted', 'Unknown')}")

        print(f"\nSkipped (low match): {len(result['skipped'])}")
        for s in result['skipped'][:10]:
            print(f"  ✗ {s['title'][:60]} ({s['match_pct']:.1f}%) | Posted: {s.get('posted', 'Unknown')}")

        print(f"\nErrors: {len(result['errors'])}")
        for e in result['errors']:
            print(f"  ! {e.get('title', 'Unknown')[:60]}: {e.get('error', 'Unknown')}")


if __name__ == "__main__":
    asyncio.run(main())