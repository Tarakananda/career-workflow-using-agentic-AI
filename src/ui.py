"""
Live Terminal UI for Job Agent using Rich.
Provides real-time updating table with spinners and status updates.
"""
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.text import Text
from rich import box
from rich.console import Group
import time


class JobStatus(Enum):
    FETCHING = "fetching"
    ANALYZING = "analyzing"
    APPLYING = "applying"
    APPLIED = "applied"
    SKIPPED_MISMATCH = "skipped_mismatch"
    SKIPPED_QUESTIONS = "skipped_questions"
    SKIPPED_OLD = "skipped_old"
    SKIPPED_IRRELEVANT = "skipped_irrelevant"
    SKIPPED_LOCATION = "skipped_location"
    ERROR = "error"
    COMPANY_SITE = "company_site"


@dataclass
class JobRow:
    id: int
    title: str = ""
    company: str = ""
    experience: str = ""
    match_pct: float = 0.0
    missing_skills: list = field(default_factory=list)
    must_have_skills: list = field(default_factory=list)
    good_to_have_skills: list = field(default_factory=list)
    status: JobStatus = JobStatus.FETCHING
    error_msg: str = ""
    _spinner_frame: int = 0

    SPINNERS = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def get_status_display(self) -> Text:
        spinner = self.SPINNERS[self._spinner_frame % len(self.SPINNERS)]
        
        if self.status == JobStatus.FETCHING:
            return Text(f"{spinner} Fetching JD...", style="cyan")
        elif self.status == JobStatus.ANALYZING:
            return Text(f"{spinner} Analyzing... {self.match_pct:.0f}%", style="yellow")
        elif self.status == JobStatus.APPLYING:
            return Text(f"{spinner} Applying...", style="magenta")
        elif self.status == JobStatus.APPLIED:
            return Text("✓ Applied", style="green bold")
        elif self.status == JobStatus.COMPANY_SITE:
            return Text("→ Company Site", style="blue bold")
        elif self.status == JobStatus.SKIPPED_MISMATCH:
            missing = ", ".join(self.missing_skills[:3])
            return Text(f"✗ Skipped: Missing {missing}", style="red")
        elif self.status == JobStatus.SKIPPED_QUESTIONS:
            return Text("✗ Skipped: Unanswered questions", style="red")
        elif self.status == JobStatus.SKIPPED_OLD:
            return Text("✗ Skipped: Too old", style="dim")
        elif self.status == JobStatus.SKIPPED_IRRELEVANT:
            return Text("✗ Skipped: Duplicate/Filtered", style="dim")
        elif self.status == JobStatus.SKIPPED_LOCATION:
            return Text(f"✗ Skipped: Location {self.error_msg}", style="yellow")
        elif self.status == JobStatus.ERROR:
            return Text(f"⚠ Error: {self.error_msg[:40]}", style="red bold")
        return Text(str(self.status.value), style="white")

    def tick_spinner(self):
        self._spinner_frame += 1


class LiveJobTable:
    def __init__(self, console: Optional[Console] = None, max_rows: int = 50, collector=None):
        self.collector = collector
        self.seen_signatures = set()  # Track signatures in current UI session
        self.console = console or Console()
        self.max_rows = max_rows
        self.rows: dict[int, JobRow] = {}
        self.live: Optional[Live] = None
        self._total_jobs = 0
        self._processed = 0
        self._applied = 0
        self._skipped = 0
        self._errors = 0
        self._start_time = time.time()
        
        if collector:
            self._load_current_run_data()
    
    def _create_signature(self, job: dict) -> str:
        """Create signature for duplicate detection in UI"""
        return "|".join([
            job.get("title", "").strip().lower(),
            job.get("company", "").strip().lower(),
            ",".join(sorted(job.get("must_have_skills", []))),
            ",".join(sorted(job.get("good_to_have_skills", []))),
        ])
    
    def _load_current_run_data(self):
        """Load jobs from CURRENT RUN (collector.jobs_data) into UI table"""
        if not self.collector:
            return
            
        for i, job in enumerate(self.collector.jobs_data):
            sig = self._create_signature(job)
            if sig in self.seen_signatures:
                continue
            self.seen_signatures.add(sig)
            
            row = JobRow(id=i, title=job.get('title', ''))
            row.company = job.get('company', '')
            row.experience = job.get('experience', '')
            row.must_have_skills = job.get('must_have_skills', [])
            row.good_to_have_skills = job.get('good_to_have_skills', [])
            row.match_pct = job.get('match_percentage', 0)
            row.missing_skills = job.get('missing_skills', [])
            
            # Map status string to JobStatus enum
            status_map = {
                'applied': JobStatus.APPLIED,
                'company_site': JobStatus.COMPANY_SITE,
                'skipped_old': JobStatus.SKIPPED_OLD,
                'skipped_irrelevant': JobStatus.SKIPPED_IRRELEVANT,
                'skipped_location': JobStatus.SKIPPED_LOCATION,
                'skipped_mismatch': JobStatus.SKIPPED_MISMATCH,
                'error': JobStatus.ERROR,
                'failed': JobStatus.ERROR,
            }
            row.status = status_map.get(job.get('status', 'skipped'), JobStatus.SKIPPED_MISMATCH)
            row.error_msg = job.get('error', '')
            
            self.rows[i] = row
        
        self._total_jobs = len(self.rows)
        self._processed = len(self.rows)

    def start(self):
        self._start_time = time.time()
        # Use auto_refresh for spinner animation - no separate thread needed
        self.live = Live(
            self._render_table(), 
            console=self.console, 
            refresh_per_second=10, 
            transient=False,
            auto_refresh=True
        )
        self.live.start()

    def stop(self):
        if self.live:
            self.live.stop()
            self.live = None

    def add_job(self, job_id: int, title: str = "", job_data: dict = None) -> JobRow:
        """Add job with optional full data for duplicate check"""
        if job_data:
            sig = self._create_signature(job_data)
            if sig in self.seen_signatures:
                return None  # Duplicate - don't add
            self.seen_signatures.add(sig)
        
        row = JobRow(id=job_id, title=title)
        self.rows[job_id] = row
        self._total_jobs += 1
        if self.live:
            self.live.update(self._render_table())
        return row

    def update_job(self, job_id: int, **kwargs):
        if job_id in self.rows:
            row = self.rows[job_id]
            for key, value in kwargs.items():
                if hasattr(row, key):
                    setattr(row, key, value)
            # Tick spinner for active statuses
            if row.status in (JobStatus.FETCHING, JobStatus.ANALYZING, JobStatus.APPLYING):
                row.tick_spinner()
            if self.live:
                self.live.update(self._render_table())

    def increment_processed(self, status: JobStatus):
        self._processed += 1
        if status == JobStatus.APPLIED or status == JobStatus.COMPANY_SITE:
            self._applied += 1
        elif status in (JobStatus.SKIPPED_MISMATCH, JobStatus.SKIPPED_QUESTIONS, 
                      JobStatus.SKIPPED_OLD, JobStatus.SKIPPED_IRRELEVANT, JobStatus.SKIPPED_LOCATION):
            self._skipped += 1
        elif status == JobStatus.ERROR:
            self._errors += 1
        if self.live:
            self.live.update(self._render_table())

    def _render_table(self) -> Table:
        table = Table(
            title="[bold blue]Job Agent - Live Processing[/bold blue]",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold cyan",
            expand=True,
        )
        
        table.add_column("Title", style="white", max_width=35, overflow="ellipsis")
        table.add_column("Company", style="white", max_width=20, overflow="ellipsis")
        table.add_column("Experience", style="white", max_width=12, overflow="ellipsis")
        table.add_column("Must Have", style="white", max_width=25, overflow="ellipsis")
        table.add_column("Good to Have", style="white", max_width=25, overflow="ellipsis")
        table.add_column("Status", style="white", max_width=40, overflow="ellipsis")
        
        sorted_rows = sorted(self.rows.values(), key=lambda r: r.id)
        for row in sorted_rows[-self.max_rows:]:
            must_have = ", ".join(row.must_have_skills[:3])[:24]
            good_to_have = ", ".join(row.good_to_have_skills[:3])[:24]
            table.add_row(
                row.title[:34],
                row.company[:19],
                row.experience[:11],
                must_have,
                good_to_have,
                row.get_status_display()
            )
        
        summary = Table.grid(padding=(0, 2))
        summary.add_column(style="green")
        summary.add_column(style="yellow")
        summary.add_column(style="red")
        summary.add_column(style="cyan")
        summary.add_row(
            f"✓ Applied: {self._applied}",
            f"✗ Skipped: {self._skipped}",
            f"⚠ Errors: {self._errors}",
            f"📋 Total: {self._processed}/{self._total_jobs}"
        )
        
        return Group(table, "", summary)

    def print_final_summary(self):
        self.stop()
        self.console.print()
        self.console.print(self._render_table())


def create_ui(collector=None) -> LiveJobTable:
    return LiveJobTable(collector=collector)