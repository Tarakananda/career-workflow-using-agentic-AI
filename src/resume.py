from pathlib import Path
from pydantic import BaseModel
from typing import Optional
import pdfplumber
import re


class Resume(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    linkedin: Optional[str] = None
    summary: str
    skills: list[str]
    experience: list["Experience"]
    education: list["Education"]

    class Config:
        arbitrary_types_allowed = True


class Experience(BaseModel):
    title: str
    company: str
    start_date: str
    end_date: Optional[str] = None
    description: str
    skills_used: list[str] = []


class Education(BaseModel):
    degree: str
    institution: str
    graduation_year: Optional[int] = None
    gpa: Optional[float] = None


def parse_resume(path: Path) -> Resume:
    """Parse resume from PDF or text file."""
    if path.suffix == ".pdf":
        text = _extract_pdf_text(path)
    else:
        text = path.read_text()
    return _parse_text_to_resume(text)


def _extract_pdf_text(path: Path) -> str:
    text = ""
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text += page.extract_text() or ""
    return text


def _parse_text_to_resume(text: str) -> Resume:
    """Parse resume text into structured data."""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    
    name = lines[0] if lines else "Unknown"
    email = _extract_email(text)
    phone = _extract_phone(text)
    linkedin = _extract_linkedin(text)
    skills = _extract_skills(text)
    experience = _extract_experience(text)
    education = _extract_education(text)
    summary = _extract_summary(text)
    
    return Resume(
        name=name,
        email=email,
        phone=phone,
        linkedin=linkedin,
        summary=summary,
        skills=skills,
        experience=experience,
        education=education,
    )


def _extract_email(text: str) -> str:
    match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", text)
    return match.group(0) if match else ""


def _extract_phone(text: str) -> Optional[str]:
    match = re.search(r"[\+]?[(]?[0-9]{3}[)]?[-\s\.]?[0-9]{3}[-\s\.]?[0-9]{4,6}", text)
    return match.group(0) if match else None


def _extract_linkedin(text: str) -> Optional[str]:
    match = re.search(r"linkedin\.com/in/[\w\-]+", text, re.I)
    return match.group(0) if match else None


def _extract_skills(text: str) -> list[str]:
    common_skills = [
        "python", "javascript", "typescript", "java", "go", "golang", "rust",
        "react", "vue", "angular", "node.js", "nodejs", "django", "flask", "fastapi",
        "aws", "gcp", "google cloud", "azure", "docker", "kubernetes", "k8s", "terraform",
        "sql", "postgresql", "postgres", "mongodb", "redis", "elasticsearch", "mysql",
        "git", "ci/cd", "cicd", "github actions", "gitlab ci", "jenkins",
        "linux", "bash", "shell", "ansible", "prometheus", "grafana", "datadog",
        "microservices", "rest api", "graphql", "grpc", "kafka", "rabbitmq",
        "devops", "sre", "site reliability", "observability", "monitoring", "logging",
        "cloudformation", "helm", "argocd", "flux", "istio", "linkerd",
        "nginx", "apache", "haproxy", "load balancer", "cdn",
        "c++", "c#", ".net", "scala", "kotlin",
        "spring boot", "spring", "hibernate", "jpa",
        "express", "koa", "nestjs", "nextjs", "nuxt", "svelte",
        "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch", "keras",
        "spark", "hadoop", "flink", "airflow", "dbt",
        "snowflake", "bigquery", "redshift", "databricks",
        "infrastructure as code", "iac", "gitops",
        "helm", "argocd", "prometheus", "grafana", "elk", "efk",
        "ansible", "terraform", "packer", "vagrant",
        "jenkins", "circleci", "travis", "github actions", "gitlab ci",
        "kubernetes", "k8s", "docker", "containerd", "podman",
        "aws", "ec2", "s3", "rds", "lambda", "ecs", "eks", "fargate",
        "gcp", "gke", "cloud run", "cloud functions",
        "azure", "aks", "functions", "devops",
        "linux", "unix", "bash", "shell", "powershell",
        "networking", "tcp/ip", "dns", "http", "https", "ssl", "tls",
        "security", "iam", "rbac", "vpn", "firewall",
        "linux", "unix", "ubuntu", "centos", "rhel", "debian",
        "databricks", "pyspark", "delta lake", "mlflow", "airflow",
        "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch", "keras",
        "kubecost", "velero", "pagerduty", "alertmanager", "thanos", "cortex", "mimir",
        "victoria metrics", "loki", "tempo", "datadog", "cloudwatch", "trivy",
        "vault", "hashicorp vault", "aws secrets manager", "azure key vault",
        "istio", "linkerd", "service mesh", "docker", "kubernetes", "containerd",
        "python", "go", "golang", "bash", "shell", "powershell",
        "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch", "keras",
        "helm", "argocd", "prometheus", "grafana", "elk", "efk",
        "ansible", "terraform", "packer", "vagrant",
        "jenkins", "circleci", "travis", "github actions", "gitlab ci",
        "kubernetes", "k8s", "docker", "containerd", "podman",
        "aws", "ec2", "s3", "rds", "lambda", "ecs", "eks", "fargate",
        "gcp", "gke", "cloud run", "cloud functions",
        "azure", "aks", "functions", "devops",
        "linux", "unix", "bash", "shell", "powershell",
        "networking", "tcp/ip", "dns", "http", "https", "ssl", "tls",
        "security", "iam", "rbac", "vpn", "firewall",
        "databricks", "pyspark", "delta lake", "mlflow", "airflow",
        "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch", "keras",
        "kubecost", "velero", "pagerduty", "alertmanager", "thanos", "cortex", "mimir",
        "victoria metrics", "loki", "tempo", "datadog", "cloudwatch", "trivy",
        "vault", "hashicorp vault", "aws secrets manager", "azure key vault",
        "istio", "linkerd", "service mesh", "docker", "kubernetes", "containerd",
        "python", "go", "golang", "bash", "shell", "powershell",
        "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch", "keras",
        "helm", "argocd", "prometheus", "grafana", "elk", "efk",
        "ansible", "terraform", "packer", "vagrant",
        "jenkins", "circleci", "travis", "github actions", "gitlab ci",
        "kubernetes", "k8s", "docker", "containerd", "podman",
        "aws", "ec2", "s3", "rds", "lambda", "ecs", "eks", "fargate",
        "gcp", "gke", "cloud run", "cloud functions",
        "azure", "aks", "functions", "devops",
        "linux", "unix", "bash", "shell", "powershell",
        "networking", "tcp/ip", "dns", "http", "https", "ssl", "tls",
        "security", "iam", "rbac", "vpn", "firewall",
        "linux", "unix", "ubuntu", "centos", "rhel", "debian",
        "databricks", "pyspark", "delta lake", "mlflow", "airflow",
        "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch", "keras",
        "kubecost", "velero", "pagerduty", "alertmanager", "thanos", "cortex", "mimir",
        "victoria metrics", "loki", "tempo", "datadog", "cloudwatch", "trivy",
        "vault", "hashicorp vault", "aws secrets manager", "azure key vault",
        "istio", "linkerd", "service mesh", "docker", "kubernetes", "containerd",
        "python", "go", "golang", "bash", "shell", "powershell",
        "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch", "keras",
        "helm", "argocd", "prometheus", "grafana", "elk", "efk",
        "ansible", "terraform", "packer", "vagrant",
        "jenkins", "circleci", "travis", "github actions", "gitlab ci",
        "kubernetes", "k8s", "docker", "containerd", "podman",
        "aws", "ec2", "s3", "rds", "lambda", "ecs", "eks", "fargate",
        "gcp", "gke", "cloud run", "cloud functions",
        "azure", "aks", "functions", "devops",
        "linux", "unix", "bash", "shell", "powershell",
        "networking", "tcp/ip", "dns", "http", "https", "ssl", "tls",
        "security", "iam", "rbac", "vpn", "firewall",
        "databricks", "pyspark", "delta lake", "mlflow", "airflow",
        "kubecost", "velero", "pagerduty", "alertmanager", "thanos", "cortex", "mimir",
        "victoria metrics", "loki", "tempo", "datadog", "cloudwatch", "trivy",
        "vault", "hashicorp vault", "aws secrets manager", "azure key vault",
        "istio", "linkerd", "service mesh", "docker", "kubernetes", "containerd",
        "python", "go", "golang", "bash", "shell", "powershell",
        "helm", "argocd", "prometheus", "grafana", "elk", "efk",
        "ansible", "terraform", "packer", "vagrant",
        "jenkins", "circleci", "travis", "github actions", "gitlab ci",
        "kubernetes", "k8s", "docker", "containerd", "podman",
        "aws", "ec2", "s3", "rds", "lambda", "ecs", "eks", "fargate",
        "gcp", "gke", "cloud run", "cloud functions",
        "azure", "aks", "functions", "devops",
        "linux", "unix", "bash", "shell", "powershell",
        "networking", "tcp/ip", "dns", "http", "https", "ssl", "tls",
        "security", "iam", "rbac", "vpn", "firewall",
        "linux", "unix", "ubuntu", "centos", "rhel", "debian",
        "databricks", "pyspark", "delta lake", "mlflow", "airflow",
        "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch", "keras",
        "kubecost", "velero", "pagerduty", "alertmanager", "thanos", "cortex", "mimir",
        "victoria metrics", "loki", "tempo", "datadog", "cloudwatch", "trivy",
        "vault", "hashicorp vault", "aws secrets manager", "azure key vault",
        "istio", "linkerd", "service mesh", "docker", "kubernetes", "containerd",
        "python", "go", "golang", "bash", "shell", "powershell",
        "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch", "keras",
        "helm", "argocd", "prometheus", "grafana", "elk", "efk",
        "ansible", "terraform", "packer", "vagrant",
        "jenkins", "circleci", "travis", "github actions", "gitlab ci",
        "kubernetes", "k8s", "docker", "containerd", "podman",
        "aws", "ec2", "s3", "rds", "lambda", "ecs", "eks", "fargate",
        "gcp", "gke", "cloud run", "cloud functions",
        "azure", "aks", "functions", "devops",
        "linux", "unix", "bash", "shell", "powershell",
        "networking", "tcp/ip", "dns", "http", "https", "ssl", "tls",
        "security", "iam", "rbac", "vpn", "firewall",
    ]
    
    text_lower = text.lower()
    found = []
    for skill in common_skills:
        if skill in text_lower:
            found.append(skill)
    
    # Deduplicate
    return list(dict.fromkeys(found))


def _extract_experience(text: str) -> list[Experience]:
    """Extract work experience from resume text."""
    experiences = []
    
    # Look for common patterns
    lines = text.split("\n")
    current_exp = {}
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Check for date patterns (e.g., "2021 - Present", "Jan 2020 - Dec 2022")
        date_match = re.search(r"(\d{4})\s*[-–]\s*(\d{4}|[Pp]resent|[Cc]urrent)", line)
        if date_match:
            if current_exp.get("title"):
                experiences.append(_build_experience(current_exp))
            current_exp = {
                "start_date": date_match.group(1),
                "end_date": date_match.group(2) if date_match.group(2).lower() != "present" else "Present",
            }
            continue
        
        # Look for title/company patterns
        if not current_exp.get("title") and any(kw in line.lower() for kw in ["engineer", "developer", "architect", "lead", "manager", "consultant", "analyst"]):
            current_exp["title"] = line
            continue
        
        if current_exp.get("title") and not current_exp.get("company"):
            if any(kw in line.lower() for kw in ["technologies", "solutions", "systems", "services", "inc", "ltd", "pvt", "corporation", "company"]):
                current_exp["company"] = line
                continue
    
    if current_exp.get("title"):
        experiences.append(_build_experience(current_exp))
    
    return experiences[:5]  # Limit to 5 most recent


def _build_experience(exp_dict: dict) -> Experience:
    skills_used = _extract_skills(exp_dict.get("description", ""))
    return Experience(
        title=exp_dict.get("title", ""),
        company=exp_dict.get("company", ""),
        start_date=exp_dict.get("start_date", ""),
        end_date=exp_dict.get("end_date"),
        description=exp_dict.get("description", ""),
        skills_used=skills_used,
    )


def _extract_education(text: str) -> list[Education]:
    education = []
    lines = text.split("\n")
    
    for line in lines:
        line = line.strip()
        if any(kw in line.lower() for kw in ["bachelor", "master", "b.tech", "m.tech", "b.e.", "m.e.", "b.sc", "m.sc", "phd", "degree"]):
            education.append(Education(
                degree=line,
                institution="",
                graduation_year=None,
            ))
    
    return education


def _extract_summary(text: str) -> str:
    # Try to find a summary section
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if any(kw in line.lower() for kw in ["summary", "profile", "objective", "about"]):
            # Return next few lines
            summary_lines = []
            for j in range(i + 1, min(i + 5, len(lines))):
                if lines[j].strip():
                    summary_lines.append(lines[j].strip())
            return " ".join(summary_lines)
    return ""