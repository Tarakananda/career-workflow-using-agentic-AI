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
        """Print jobs in table format with auto-adjusting columns."""
        if not self.jobs_data:
            print("No jobs to display")
            return
        
        import shutil
        term_width = shutil.get_terminal_size().columns
        term_width = max(term_width, 100)  # Minimum width
        
        # Column definitions with min/max widths
        columns = [
            ("Title", 20, 35),
            ("Location", 12, 22),
            ("Salary", 10, 16),
            ("Exp", 7, 10),
            ("Missing Skills", 18, 30),
            ("Status", 10, 12),
        ]
        
        # Calculate widths proportionally
        total_min = sum(c[1] for c in columns)
        total_max = sum(c[2] for c in columns)
        available = term_width - len(columns) * 3 - 2  # borders + padding
        
        if available >= total_max:
            widths = [c[2] for c in columns]
        elif available <= total_min:
            widths = [c[1] for c in columns]
        else:
            # Proportional distribution
            ratio = (available - total_min) / (total_max - total_min)
            widths = [int(c[1] + (c[2] - c[1]) * ratio) for c in columns]
        
        # Build format string
        fmt = " │ ".join(f"{{:<{w}}}" for w in widths)
        sep = "─┼─".join("─" * w for w in widths)
        
        # Header
        headers = [c[0] for c in columns]
        print(fmt.format(*headers))
        print(f"─{sep}─")
        
        # Rows
        for job in self.jobs_data:
            title = job.get('title', 'N/A')[:widths[0]-1]
            location = job.get('location', 'N/A')[:widths[1]-1]
            salary = job.get('salary', 'N/A')[:widths[2]-1]
            exp = job.get('experience', 'N/A')[:widths[3]-1]
            missing = ', '.join(job.get('missing_skills', [])[:3])[:widths[4]-1]
            applied = job.get('applied', False)
            status = job.get('status', 'skipped')
            
            if status == 'applied' or status == 'company_site':
                status_str = "✓ Applied"
            elif status == 'error':
                status_str = "⚠ Error"
            elif status == 'failed':
                status_str = "✗ Failed"
            else:
                status_str = "✗ Skipped"
            
            status_str = status_str[:widths[5]-1]
            
            print(fmt.format(title, location, salary, exp, missing, status_str))

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