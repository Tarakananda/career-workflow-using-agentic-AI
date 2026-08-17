from pathlib import Path
from typing import Any
import json
from datetime import datetime

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False


class JobDataCollector:
    def __init__(self, output_dir: Path = Path("output")):
        self.output_dir = output_dir
        self.output_dir.mkdir(exist_ok=True)
        self.jobs_data = []

    def get_day_filename(self) -> str:
        """Generate filename like day_1.json, day_2.json based on existing files."""
        existing_days = []
        for f in self.output_dir.glob("day_*.json"):
            try:
                day_num = int(f.stem.split("_")[1])
                existing_days.append(day_num)
            except (ValueError, IndexError):
                continue
        
        next_day = max(existing_days) + 1 if existing_days else 1
        return f"day_{next_day}.json"

    def add_job(self, job_data: dict[str, Any]) -> None:
        """Add job data to collection."""
        self.jobs_data.append(job_data)

    def save(self) -> Path:
        """Save collected jobs to file."""
        filename = self.get_day_filename()
        filepath = self.output_dir / filename
        
        output = {
            "date": datetime.now().isoformat(),
            "day": filename.replace(".json", ""),
            "total_jobs": len(self.jobs_data),
            "jobs": self.jobs_data
        }
        
        filepath.write_text(json.dumps(output, indent=2, ensure_ascii=False))
        print(f"Saved {len(self.jobs_data)} jobs to {filepath}")
        return filepath

    def print_table(self) -> None:
        """Print jobs in table format."""
        if not self.jobs_data:
            print("No jobs to display")
            return
        
        print(f"\n{'='*120}")
        print(f"{'ROLE':<30} {'COMPANY':<25} {'EXP':<10} {'MISSING SKILLS':<35} {'JD PREVIEW'}")
        print(f"{'='*120}")
        
        for job in self.jobs_data:
            role = job.get('role', '')[:29]
            company = job.get('company', '')[:24]
            exp = job.get('experience', '')[:9]
            missing = ', '.join(job.get('missing_skills', [])[:5])
            missing = missing[:34]
            jd_preview = job.get('jd_text', '')[:80].replace('\n', ' ')
            
            print(f"{role:<30} {company:<25} {exp:<10} {missing:<35} {jd_preview}")

    def clear(self) -> None:
        """Clear collected data."""
        self.jobs_data = []


def create_collector() -> JobDataCollector:
    """Factory function to create collector."""
    return JobDataCollector()


class ManualApplyCollector:
    def __init__(self, output_dir: Path = Path("output")):
        self.output_dir = output_dir
        self.output_dir.mkdir(exist_ok=True)
        self.jobs_data = []
    
    def add_job(self, job_data: dict[str, Any]) -> None:
        self.jobs_data.append(job_data)
    
    def save_excel(self) -> Path:
        if not PANDAS_AVAILABLE:
            print("pandas not available, skipping Excel export")
            return None
        
        df = pd.DataFrame(self.jobs_data)
        cols = [
            "role", "title", "company", "posted_date", "experience",
            "location", "match_percentage", "matched_skills", "missing_skills",
            "naukri_url", "company_site_url", "status", "timestamp"
        ]
        df = df[[c for c in cols if c in df.columns]]
        
        filename = f"manual_apply_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        filepath = self.output_dir / filename
        df.to_excel(filepath, index=False)
        print(f"Saved {len(self.jobs_data)} manual apply jobs to {filepath}")
        return filepath
    
    def print_table(self) -> None:
        if not self.jobs_data:
            return
        print(f"\n{'='*100}")
        print(f"MANUAL APPLY NEEDED ({len(self.jobs_data)} jobs)")
        print(f"{'='*100}")
        for job in self.jobs_data:
            print(f"  {job['title'][:50]} | {job['company'][:20]} | {job['match_percentage']}% | {job['naukri_url']}")