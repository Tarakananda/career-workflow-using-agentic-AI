"""
Enhanced Weighted Skill Matcher v2
Implements category-based weighted scoring for >80% match accuracy
"""
import re
from typing import Optional, Dict, List, Tuple, Set
from dataclasses import dataclass


@dataclass
class SkillCategory:
    name: str
    skills: Set[str]
    weight: float  # Required (1.5) vs Nice-to-have (1.0)
    required: bool  # True for must-have skills


# Skill categories with weights
# Required skills (weight 1.5) are must-haves for the role
# Nice-to-have skills (weight 1.0) boost score but aren't mandatory
SKILL_CATEGORIES = [
    SkillCategory(
        name="cloud_providers",
        skills={"aws", "azure", "gcp", "google cloud", "ec2", "eks", "aks", "gke", 
                "lambda", "cloud run", "cloud functions", "ecs", "fargate", 
                "rds", "dynamodb", "s3", "cloudformation", "iam", "vpc",
                "azure devops", "azure functions", "key vault", "app service",
                "gke", "cloud build", "artifact registry", "cloud run"},
        weight=1.5,
        required=True
    ),
    SkillCategory(
        name="container_orchestration",
        skills={"kubernetes", "eks", "aks", "gke", "helm", "kustomize", "helmfile",
                "argocd", "flux", "flux v2", "argocd", "argo workflows", "argo rollouts",
                "operator", "crd", "csi", "cni", "ingress", "istio", "linkerd",
                "service mesh", "envoy", "gateway api"},
        weight=1.5,
        required=True
    ),
    SkillCategory(
        name="ci_cd",
        skills={"jenkins", "github actions", "gitlab ci", "azure devops", "argo workflows",
                "circleci", "travis", "bitbucket pipelines", "codebuild", "codepipeline",
                "tekton", "concourse", "spinnaker", "harness", "drone"},
        weight=1.3,
        required=True
    ),
    SkillCategory(
        name="gitops",
        skills={"argocd", "flux", "flux v2", "helmfile", "kustomize", "kustomize overlays",
                "argocd applications", "argocd projects", "argocd notifications",
                "flux kustomization", "flux helmrelease", "weave flux"},
        weight=1.3,
        required=True
    ),
    SkillCategory(
        name="iac",
        skills={"terraform", "terragrunt", "cloudformation", "pulumi", "ansible",
                "packer", "crossplane", "cdktf", "cdk", "bicep", "arm templates",
                "tfstate", "terraform modules", "terraform workspaces", "terraform cloud"},
        weight=1.3,
        required=True
    ),
    SkillCategory(
        name="monitoring_observability",
        skills={"prometheus", "grafana", "loki", "tempo", "alertmanager", "pagerduty",
                "datadog", "cloudwatch", "new relic", "splunk", "elk", "efk",
                "elastic stack", "opentelemetry", "jaeger", "zipkin", "x-ray",
                "alertmanager", "thanos", "cortex", "mimir", "victoria metrics"},
        weight=1.2,
        required=False
    ),
    SkillCategory(
        name="security",
        skills={"trivy", "sonarqube", "cosign", "kyverno", "opa", "gatekeeper",
                "vault", "hashicorp vault", "aws secrets manager", "azure key vault",
                "gcp secret manager", "rbac", "mtls", "istio", "linkerd", "cert-manager",
                "cosign", "syft", "grype", "aquasec", "sysdig", "falco",
                "kube-bench", "kube-hunter", "kubernetes security"},
        weight=1.2,
        required=False
    ),
    SkillCategory(
        name="scripting",
        skills={"python", "go", "golang", "bash", "shell", "powershell", "boto3",
                "azure sdk", "gcp sdk", "aws sdk", "kubernetes client-go",
                "terraform provider", "ansible module", "fastapi", "flask", "click"},
        weight=1.1,
        required=False
    ),
    SkillCategory(
        name="databases",
        skills={"postgresql", "mysql", "redis", "dynamodb", "mongodb", "cassandra",
                "elasticsearch", "opensearch", "rda", "aurora", "cosmos db",
                "cloudsql", "firestore", "bigtable", "spanner"},
        weight=1.0,
        required=False
    ),
    SkillCategory(
        name="networking",
        skills={"vpc", "subnet", "security group", "nacl", "alb", "nlb", "clb",
                "route 53", "cloudfront", "api gateway", "vpn", "direct connect",
                "transit gateway", "vpc peering", "privatelink", "dns", "ssl", "tls",
                "acm", "certificate manager", "waf", "shield", "ddos protection"},
        weight=1.0,
        required=False
    ),
    SkillCategory(
        name="containerization",
        skills={"docker", "containerd", "podman", "buildah", "kaniko", "buildkit",
                "dockerfile", "multistage build", "distroless", "scratch",
                "container security", "trivy", "syft", "grype", "cosign", "kyverno"},
        weight=1.2,
        required=True
    ),
    SkillCategory(
        name="serverless",
        skills={"lambda", "cloud functions", "cloud run", "azure functions",
                "step functions", "eventbridge", "sqs", "sns", "pubsub",
                "event grid", "functions framework", "knative", "openfaas"},
        weight=1.0,
        required=False
    ),
    SkillCategory(
        name="finops",
        skills={"kubecost", "aws compute optimizer", "azure cost management",
                "gcp cost management", "cloudhealth", "cloudability",
                "finops", "cost optimization", "rightsizing", "savings plans",
                "reserved instances", "spot instances", "fargate spot"},
        weight=1.0,
        required=False
    ),
    SkillCategory(
        name="dr_backup",
        skills={"velero", "velero backup", "velero restore", "velero schedule",
                "cross-region", "cross-account", "dr", "disaster recovery",
                "backup", "restore", "rpo", "rto", "business continuity"},
        weight=1.0,
        required=False
    ),
]


# Skill aliases for matching variations
SKILL_ALIASES = {
    "azure cloud": "azure",
    "aws cloud": "aws",
    "google cloud": "gcp",
    "gcp": "google cloud",
    "k8s": "kubernetes",
    "kubernetes": "kubernetes",
    "ci cd": "ci/cd",
    "cicd": "ci/cd",
    "ci/cd": "ci/cd",
    "continuous integration": "ci/cd",
    "continuous deployment": "ci/cd",
    "infra as code": "infrastructure as code",
    "iac": "infrastructure as code",
    "infrastructure as code": "infrastructure as code",
    "gitops": "gitops",
    "argocd": "argocd",
    "argo cd": "argocd",
    "fluxcd": "flux",
    "flux cd": "flux",
    "helm charts": "helm",
    "kustomize": "kustomize",
    "k8s": "kubernetes",
    "eks": "eks",
    "aks": "aks",
    "gke": "gke",
    "ec2": "ec2",
    "rds": "rds",
    "s3": "s3",
    "lambda": "lambda",
    "cloudformation": "cloudformation",
    "terraform": "terraform",
    "terragrunt": "terragrunt",
    "ansible": "ansible",
    "packer": "packer",
    "jenkins": "jenkins",
    "github actions": "github actions",
    "gitlab ci": "gitlab ci",
    "azure devops": "azure devops",
    "argo cd": "argocd",
    "argo": "argo",
    "flux": "flux",
    "prometheus": "prometheus",
    "grafana": "grafana",
    "loki": "loki",
    "tempo": "tempo",
    "datadog": "datadog",
    "cloudwatch": "cloudwatch",
    "trivy": "trivy",
    "vault": "vault",
    "sonarqube": "sonarqube",
    "istio": "istio",
    "linkerd": "linkerd",
    "service mesh": "service mesh",
    "docker": "docker",
    "kubernetes": "kubernetes",
    "containerd": "containerd",
    "python": "python",
    "go": "go",
    "golang": "go",
    "bash": "bash",
    "shell": "bash",
    "terraform": "terraform",
    "terragrunt": "terragrunt",
    "ansible": "ansible",
    "packer": "packer",
    "jenkins": "jenkins",
    "github actions": "github actions",
    "gitlab ci": "gitlab ci",
    "azure devops": "azure devops",
    "argocd": "argocd",
    "flux": "flux",
    "prometheus": "prometheus",
    "grafana": "grafana",
    "loki": "loki",
    "tempo": "tempo",
    "datadog": "datadog",
    "cloudwatch": "cloudwatch",
    "trivy": "trivy",
    "vault": "vault",
    "sonarqube": "sonarqube",
    "istio": "istio",
    "linkerd": "linkerd",
    "service mesh": "service mesh",
    "docker": "docker",
    "kubernetes": "kubernetes",
    "containerd": "containerd",
    "python": "python",
    "go": "go",
    "golang": "go",
    "bash": "bash",
    "shell": "bash",
}


def normalize_skill(skill: str) -> str:
    """Normalize skill name for matching"""
    skill = skill.lower().strip()
    # Apply aliases
    for alias, canonical in SKILL_ALIASES.items():
        if alias in skill:
            return canonical
    return skill


def extract_skills_from_text(text: str) -> List[str]:
    """Extract known skills from job description text with normalization"""
    text_lower = text.lower()
    found = set()
    
    # Flatten all skills from categories
    all_skills = set()
    for cat in SKILL_CATEGORIES:
        all_skills.update(cat.skills)
    
    # Also check for common variations
    extended_skills = set(all_skills)
    for skill in all_skills:
        # Add common variations
        if " " in skill:
            extended_skills.add(skill.replace(" ", "-"))
            extended_skills.add(skill.replace(" ", ""))
        if "." in skill:
            extended_skills.add(skill.replace(".", ""))
    
    for skill in extended_skills:
        if skill in text_lower:
            found.add(normalize_skill(skill))
    
    return list(found)


def get_skill_category(skill: str) -> Optional[SkillCategory]:
    """Find which category a skill belongs to"""
    normalized = normalize_skill(skill)
    for cat in SKILL_CATEGORIES:
        if normalized in cat.skills:
            return cat
    return None


def calculate_weighted_match(resume_skills: List[str], job_skills: List[str]) -> Tuple[float, Dict]:
    """
    Calculate weighted skill match percentage.
    
    Returns: (match_percentage, details_dict)
    """
    if not job_skills:
        return 0.0, {"matched": [], "missing": [], "categories": {}}
    
    resume_set = set(normalize_skill(s) for s in resume_skills)
    job_set = set(normalize_skill(s) for s in job_skills)
    
    # Track per-category matches
    category_details = {}
    total_weight = 0.0
    matched_weight = 0.0
    
    for cat in SKILL_CATEGORIES:
        cat_job_skills = job_set & cat.skills
        if not cat_job_skills:
            continue
        
        cat_resume_skills = resume_set & cat.skills
        cat_matched = cat_resume_skills & cat_job_skills
        cat_missing = cat_job_skills - cat_resume_skills
        
        cat_weight = len(cat_job_skills) * cat.weight
        cat_matched_weight = len(cat_matched) * cat.weight
        
        total_weight += cat_weight
        matched_weight += cat_matched_weight
        
        category_details[cat.name] = {
            "required": cat.required,
            "weight": cat.weight,
            "job_skills": list(cat_job_skills),
            "matched": list(cat_matched),
            "missing": list(cat_missing),
            "score": (cat_matched_weight / cat_weight * 100) if cat_weight > 0 else 100
        }
    
    # Overall match percentage
    match_pct = (matched_weight / total_weight * 100) if total_weight > 0 else 0.0
    
    # Flatten matched/missing for compatibility
    all_matched = set()
    all_missing = set()
    for cat in category_details.values():
        all_matched.update(cat["matched"])
        all_missing.update(cat["missing"])
    
    details = {
        "matched": list(all_matched),
        "missing": list(all_missing),
        "categories": category_details,
        "total_weight": total_weight,
        "matched_weight": matched_weight
    }
    
    return match_pct, details


def should_apply(resume_skills: List[str], job_description: str, threshold: float = 80.0) -> Tuple[bool, float, List[str], List[str]]:
    """Determine if should apply based on weighted skill match."""
    job_skills = extract_skills_from_text(job_description)
    match_pct, details = calculate_weighted_match(resume_skills, job_skills)
    
    # Check required categories - must have at least 50% in each required category
    for cat_name, cat_details in details["categories"].items():
        if cat_details["required"] and cat_details["score"] < 50:
            # Fail if required category is below 50%
            match_pct = min(match_pct, 79.9)  # Force below threshold
            break
    
    matched = details["matched"]
    missing = details["missing"]
    
    return match_pct >= threshold, match_pct, matched, missing


def get_missing_required_skills(resume_skills: List[str], job_description: str) -> List[str]:
    """Get list of missing required skills that are critical for the role"""
    job_skills = extract_skills_from_text(job_description)
    _, details = calculate_weighted_match(resume_skills, job_skills)
    
    missing_required = []
    for cat_name, cat_details in details["categories"].items():
        if cat_details["required"]:
            missing_required.extend(cat_details["missing"])
    
    return missing_required


# For backward compatibility
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


if __name__ == "__main__":
    # Test the matcher
    resume = ["aws", "azure", "kubernetes", "terraform", "jenkins", "github actions", 
              "docker", "helm", "argocd", "python", "go", "prometheus", "grafana",
              "terraform", "ansible", "linux", "git", "ci/cd"]
    
    job_desc = """
    We are looking for a Cloud & DevOps Engineer with experience in AWS, Azure, Kubernetes,
    Terraform, Jenkins, GitHub Actions, Docker, Helm, ArgoCD, Python, Go, Prometheus, Grafana,
    Ansible, Linux, Git, CI/CD, CloudFormation, Helm, ArgoCD, Prometheus, Grafana, Loki, Tempo,
    Datadog, Trivy, Vault, Istio, Python, Go, Bash, Terraform, Terragrunt, Helm, Kustomize.
    """
    
    should, pct, matched, missing = should_apply(resume, job_desc, 80.0)
    print(f"Should apply: {should}")
    print(f"Match: {pct:.1f}%")
    print(f"Matched: {matched}")
    print(f"Missing: {missing}")