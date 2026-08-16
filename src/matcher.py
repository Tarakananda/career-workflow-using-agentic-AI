import re
from typing import Optional


def parse_posted_date(date_str: str) -> Optional[int]:
    """Parse posted date string and return days ago as int. Returns None if can't parse."""
    date_str = date_str.lower().strip()
    
    if "hour" in date_str or "hr" in date_str or "just now" in date_str or "few hour" in date_str:
        return 0  # Less than a day
    
    if "today" in date_str:
        return 0
    
    if "day" in date_str:
        match = re.search(r"(\d+)\s*day", date_str)
        if match:
            return int(match.group(1))
        if "a day" in date_str or "1 day" in date_str:
            return 1
    
    if "week" in date_str:
        match = re.search(r"(\d+)\s*week", date_str)
        if match:
            return int(match.group(1)) * 7
        return 7
    
    if "month" in date_str:
        return 30
    
    return None


def is_recent_job(date_str: str, max_days: int = 2) -> bool:
    """Check if job was posted within max_days."""
    days = parse_posted_date(date_str)
    if days is None:
        return False
    return days <= max_days


def extract_skills_from_text(text: str) -> list[str]:
    """Extract known skills from job description text."""
    common_skills = [
        "python", "javascript", "typescript", "java", "go", "golang", "rust",
        "react", "vue", "angular", "node.js", "nodejs", "django", "flask", "fastapi",
        "aws", "gcp", "google cloud", "azure", "docker", "kubernetes", "k8s", "terraform",
        "sql", "postgresql", "postgres", "mongodb", "redis", "elasticsearch", "mysql",
        "git", "ci/cd", "cicd", "github actions", "gitlab ci", "jenkins",
        "linux", "bash", "shell", "ansible", "prometheus", "grafana", "datadog",
        "microservices", "rest api", "graphql", "grpc", "message queue", "kafka", "rabbitmq",
        "devops", "sre", "site reliability", "observability", "monitoring", "logging",
        "cloudformation", "helm", "argocd", "flux", "istio", "linkerd",
        "jenkins", "circleci", "travis", "github actions", "gitlab", "bitbucket",
        "nginx", "apache", "haproxy", "load balancer", "cdn",
        "python", "java", "go", "rust", "c++", "c#", ".net", "scala", "kotlin",
        "spring boot", "spring", "hibernate", "jpa", "mybatis",
        "express", "koa", "nestjs", "nextjs", "nuxt", "svelte",
        "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch", "keras",
        "spark", "hadoop", "kafka", "flink", "airflow", "dbt",
        "snowflake", "bigquery", "redshift", "databricks",
        "ci/cd", "continuous integration", "continuous deployment",
        "infrastructure as code", "iac", "gitops",
    ]
    
    text_lower = text.lower()
    found = []
    for skill in common_skills:
        if skill in text_lower:
            found.append(skill)
    return found


def calculate_skill_match(resume_skills: list[str], job_skills: list[str]) -> float:
    """Calculate skill match percentage (job skills covered by resume)."""
    if not job_skills:
        return 0.0
    
    resume_set = set(s.lower() for s in resume_skills)
    job_set = set(s.lower() for s in job_skills)
    
    matched = resume_set & job_set
    return len(matched) / len(job_set) * 100


def should_apply(resume_skills: list[str], job_description: str, threshold: float = 80.0) -> tuple[bool, float, list[str], list[str]]:
    """Determine if should apply based on skill match."""
    job_skills = extract_skills_from_text(job_description)
    match_pct = calculate_skill_match(resume_skills, job_skills)
    
    resume_set = set(s.lower() for s in resume_skills)
    job_set = set(s.lower() for s in job_skills)
    matched = list(resume_set & job_set)
    missing = list(job_set - resume_set)
    
    return match_pct >= threshold, match_pct, matched, missing