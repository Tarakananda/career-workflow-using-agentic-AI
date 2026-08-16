#!/usr/bin/env python3
"""Main entry point for the Job Agent."""
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.search import JobSearch
from src.apply import JobApplier
from src.matcher import is_recent_job, should_apply, extract_skills_from_text
from src.resume import parse_resume


def main():
    parser = argparse.ArgumentParser(description="Job Application Agent")
    parser.add_argument("--max-jobs", type=int, default=10, help="Max jobs to process")
    parser.add_argument("--threshold", type=float, default=80.0, help="Skill match threshold %")
    parser.add_argument("--max-days", type=int, default=2, help="Max days old for job posting")
    parser.add_argument("--search-only", action="store_true", help="Only search, don't apply")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be applied without applying")
    args = parser.parse_args()

    print("=" * 60)
    print("JOB AGENT - Starting")
    print("=" * 60)

    search = JobSearch()
    jobs = search.search_jobs()
    print(f"\nTotal jobs found: {len(jobs)}")

    if args.search_only:
        for job in jobs:
            print(f"  {job['title'][:60]} | {job['company']} | {job['location']} | {job['experience']} | {job['posted_date']}")
        return

    # Load resume for skill matching
    resume = parse_resume(Path("CV_Tarakananda.pdf"))

    # Filter recent jobs
    recent_jobs = []
    for job in jobs:
        posted = job.get("posted_date", "")
        if is_recent_job(posted, args.max_days):
            recent_jobs.append(job)

    print(f"\nRecent jobs (within {args.max_days} days): {len(recent_jobs)}")

    # Title filter
    relevant_keywords = ["devops", "cloud", "sre", "site reliability", "aws", "azure", "gcp", 
                        "kubernetes", "k8s", "docker", "terraform", "ansible", "jenkins",
                        "ci/cd", "infrastructure", "platform", "reliability", "observability",
                        "prometheus", "grafana", "monitoring", "logging", "automation"]
    
    exclude_patterns = [
        "java developer", "python developer", "full stack", ".net", "dot net",
        "react", "node js", "nodejs", "angular", "vue", "frontend", "backend",
        "salesforce", "sap", "scrum master", "business analyst", "data scientist",
        "data engineer", "ml engineer", "ai engineer", "mlops", "genai", "llm",
        "network engineer", "security engineer", "support engineer", "qa engineer",
        "test engineer", "quality assurance", "php", "laravel", "wordpress",
    ]

    seen_urls = set()
    filtered_jobs = []
    for job in recent_jobs:
        url = job.get('url', '')
        if url in seen_urls:
            continue
        seen_urls.add(url)
        
        title_lower = job['title'].lower()
        
        if any(ex in title_lower for ex in exclude_patterns):
            continue
        
        if any(kw in title_lower for kw in relevant_keywords):
            filtered_jobs.append(job)

    print(f"After title filter: {len(filtered_jobs)} relevant jobs")
    
    # Limit
    filtered_jobs = filtered_jobs[:args.max_jobs]

    # Analyze each job
    print("\n" + "=" * 60)
    print("JOB ANALYSIS (DRY RUN)" if args.dry_run else "JOB ANALYSIS")
    print("=" * 60)
    
    would_apply = []
    would_skip = []
    errors = []

    for job in filtered_jobs:
        print(f"\nAnalyzing: {job['title'][:60]} at {job['company']}")
        print(f"  Posted: {job.get('posted_date', 'Unknown')}")
        print(f"  URL: {job['url']}")
        
        # We need to fetch JD to analyze - show what we'd do
        print(f"  [Would fetch JD and extract skills]")
        print(f"  [Would compare with resume skills: {resume.skills[:10]}...]")
        
        # For dry run, we can't know the match without fetching JD
        # So we'll show the job as a candidate
        would_apply.append(job)
        print(f"  >> CANDIDATE FOR APPLICATION")

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Jobs that would be processed: {len(would_apply)}")
    for i, job in enumerate(would_apply, 1):
        print(f"  {i}. {job['title'][:70]}")
        print(f"     Company: {job['company']} | Location: {job['location']} | Exp: {job['experience']}")
        print(f"     Posted: {job.get('posted_date', 'Unknown')}")
        print(f"     URL: {job['url']}")

    if args.dry_run:
        print("\n[DRY RUN] No applications submitted.")
        print("Run without --dry-run to actually apply.")


if __name__ == "__main__":
    main()