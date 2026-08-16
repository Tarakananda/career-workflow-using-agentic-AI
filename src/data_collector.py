from pathlib import Path
from typing import Any
import json
from datetime import datetime


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