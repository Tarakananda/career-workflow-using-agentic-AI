#!/usr/bin/env python3
"""
LLM-based Skill Extractor for Resume
Extracts comprehensive skill inventory with years of experience from resume text.
Uses OpenAI GPT-4o-mini for intelligent extraction.
"""
import os
import json
import re
from typing import Optional, Dict, Any, List
from pathlib import Path

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    from rapidfuzz import fuzz, process
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False


class LLMSkillExtractor:
    """Extracts skill inventory from resume using LLM."""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini", ui: Optional[Any] = None):
        self.model = model
        self.client = None
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.ui = ui
        
        if OPENAI_AVAILABLE and self.api_key:
            try:
                self.client = OpenAI(api_key=self.api_key)
            except Exception as e:
                self._debug(f"OpenAI client initialization failed: {e}")
                self.client = None
        elif OPENAI_AVAILABLE and not self.api_key:
            self._debug("No OpenAI API key provided, LLM extraction disabled")
    
    def _debug(self, msg: str) -> None:
        """Print debug message only when UI is not active (console mode)."""
        if self.ui is None:
            print(msg)
    
    def extract_skill_inventory(self, resume_text: str) -> Dict[str, str]:
        """
        Extract all skills with years of experience from resume.
        Returns: {"skill_name": "X years", ...}
        """
        if not self.client:
            self._debug("  OpenAI client not available, falling back to regex extraction")
            return self._fallback_extract(resume_text)
        
        prompt = f"""Extract ALL technical skills, tools, technologies, and platforms mentioned in this resume along with years of experience for each.

Resume text:
{resume_text[:15000]}

Return a JSON object where keys are skill names (lowercase, normalized) and values are years of experience as strings (e.g., "3 years", "5 years").

Rules:
1. Include: programming languages, cloud platforms, DevOps tools, databases, monitoring tools, CI/CD, containerization, IaC, networking, security tools, scripting, frameworks, methodologies
2. Normalize skill names: "k8s" → "kubernetes", "aws cloud" → "aws", "ci/cd" → "ci/cd", "github actions" → "github actions"
3. Extract years from experience descriptions. If not explicitly stated, estimate based on role duration.
4. Include skills from projects, certifications, and technical skills sections
5. For skills mentioned without explicit years, estimate: "3 years" (reasonable default for 3+ years exp)
6. Return ONLY valid JSON, no markdown, no explanations

Example output:
{{
  "aws": "5 years",
  "azure": "3 years",
  "kubernetes": "4 years",
  "terraform": "3 years",
  "docker": "5 years",
  "jenkins": "4 years",
  "github actions": "3 years",
  "python": "5 years",
  "prometheus": "2 years",
  "grafana": "2 years"
}}"""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert resume parser for DevOps/Cloud roles. Extract skills with years accurately."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=2000
            )
            
            content = response.choices[0].message.content.strip()
            # Clean up any markdown
            content = content.replace("```json", "").replace("```", "").strip()
            
            skill_inventory = json.loads(content)
            # Normalize keys to lowercase
            return {k.lower().strip(): v for k, v in skill_inventory.items()}
            
        except Exception as e:
            print(f"  LLM extraction failed: {e}, falling back to regex")
            return self._fallback_extract(resume_text)
    
    def _fallback_extract(self, resume_text: str) -> Dict[str, str]:
        """Regex-based fallback extraction."""
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
        ]
        
        text_lower = resume_text.lower()
        found = {}
        
        # Extract years from experience sections
        exp_years = self._estimate_total_years(resume_text)
        
        for skill in common_skills:
            if skill in text_lower:
                # Try to find specific years for this skill
                years = self._extract_years_for_skill(resume_text, skill, exp_years)
                found[skill] = years
        
        return found
    
    def _estimate_total_years(self, text: str) -> int:
        """Estimate total years of experience from resume."""
        import re
        years = []
        for match in re.finditer(r'(\d{4})\s*[-–]\s*(\d{4}|[Pp]resent|[Cc]urrent)', text):
            start = int(match.group(1))
            end_str = match.group(2)
            if 'present' in end_str.lower() or 'current' in end_str.lower():
                from datetime import datetime
                end = datetime.now().year
            else:
                end = int(end_str)
            years.append(end - start)
        return sum(years) if years else 3
    
    def _extract_years_for_skill(self, text: str, skill: str, default_years: int) -> str:
        """Try to extract years for a specific skill from context."""
        import re
        # Look for patterns like "X years of Y" or "Y (X years)"
        patterns = [
            rf'(\d+)\s*(?:years?|yrs?)\s*(?:of\s+)?{re.escape(skill)}',
            rf'{re.escape(skill)}\s*[\(:]\s*(\d+)\s*(?:years?|yrs?)',
            rf'{re.escape(skill)}.*?(\d+)\s*(?:years?|yrs?)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return f"{match.group(1)} years"
        return f"{default_years} years"
    
    def extract_skill_from_question(self, question: str) -> Optional[str]:
        """
        Extract the skill/technology being asked about in a chatbot question.
        e.g., "How many years of experience do you have in Open Text Operations Bridge Manager?"
        → "open text operations bridge manager"
        """
        if not self.client:
            return self._fallback_extract_skill(question)
        
        prompt = f"""Extract the specific skill, tool, technology, or platform being asked about in this question.

Question: "{question}"

Return ONLY the skill name (lowercase, normalized), or "unknown" if no specific skill is mentioned.

Examples:
- "How many years of experience do you have in Azure?" → "azure"
- "What is your experience with Kubernetes?" → "kubernetes"  
- "How many years of experience do you have in Open Text Operations Bridge Manager?" → "open text operations bridge manager"
- "Are you willing to relocate?" → "unknown"
- "What is your notice period?" → "unknown"
- "Rate your Terraform skills" → "terraform"

Question: "{question}"
Skill:"""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=50
            )
            skill = response.choices[0].message.content.strip().lower()
            if skill in ["unknown", "none", "n/a", ""]:
                return None
            return skill
        except Exception as e:
            self._debug(f"  LLM skill extraction failed: {e}")
            return self._fallback_extract_skill(question)
    
    def _fallback_extract_skill(self, question: str) -> Optional[str]:
        """Regex-based skill extraction from question."""
        import re
        q_lower = question.lower()
        
        # First, try to find known tech terms directly (most reliable)
        tech_terms = [
            "machine learning", "deep learning", "ai", "ml", "nlp", "computer vision",
            "open text operations bridge manager", "crowdstrike", "wiz", "barnowl",
            "aws", "azure", "gcp", "google cloud", "kubernetes", "k8s", "docker",
            "terraform", "ansible", "jenkins", "github actions", "gitlab ci",
            "prometheus", "grafana", "datadog", "python", "go", "golang", "bash",
            "helm", "argocd", "flux", "ci/cd", "ci cd", "cicd",
            "kafka", "rabbitmq", "redis", "postgresql", "mysql", "mongodb",
            "elasticsearch", "sql", "nosql", "microservices", "rest api",
            "linux", "windows", "unix", "shell", "powershell", "scripting",
            "networking", "security", "iam", "vpn", "firewall",
        ]
        for term in tech_terms:
            if term in q_lower:
                return term
        
        # Strategy: Split by common prepositions and extract skill from the end
        # Common patterns: "experience in X", "years of experience in X", "skill in X", "knowledge of X"
        prepositions = [' in ', ' with ', ' of ', ' for ']
        
        for prep in prepositions:
            if prep in q_lower:
                # Get the part after the last occurrence of the preposition
                parts = q_lower.split(prep)
                if len(parts) > 1:
                    skill_part = parts[-1].split('?')[0].strip()
                    # Remove common filler words at the start
                    skill_part = re.sub(r'^(?:do you have|you have|your|the|a|an|my)\s+', '', skill_part)
                    # Remove trailing filler
                    skill_part = re.sub(r'\s+(?:years?|yrs?|experience|please|rate|your|\?).*$', '', skill_part).strip()
                    if len(skill_part) > 2:
                        return skill_part
        
        # Fallback: try regex patterns
        patterns = [
            r'(?:years?\s+of\s+experience|experience)\s+(?:in|with|of)\s+([a-zA-Z0-9\s\+\#\.\-]{3,50}?)(?:\s+(?:years?|yrs?|\?|do|you|have|please|rate|your)|\s*$)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, q_lower)
            if match:
                skill = match.group(1).strip()
                skill = re.sub(r'\s+(?:years?|yrs?|experience|\?|do|you|have|in|the|a|an|please|rate|your).*$', '', skill).strip()
                if len(skill) > 2:
                    return skill
        
        return None


def extract_skill_inventory(resume_path: Path, api_key: Optional[str] = None) -> Dict[str, str]:
    """Main entry point to extract skill inventory from resume file."""
    # Read resume text
    import pdfplumber
    text = ""
    with pdfplumber.open(resume_path) as pdf:
        for page in pdf.pages:
            text += page.extract_text() or ""
    
    extractor = LLMSkillExtractor(api_key=api_key)
    return extractor.extract_skill_inventory(text)


if __name__ == "__main__":
    import sys
    resume_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("CV_Tarakananda_Optimized.pdf")
    skills = extract_skill_inventory(resume_path)
    print(json.dumps(skills, indent=2))