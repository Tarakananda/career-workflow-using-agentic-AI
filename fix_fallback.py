with open('src/llm_extractor.py', 'r') as f:
    content = f.read()

old = '''    def _fallback_extract_skill(self, question: str) -> Optional[str]:
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
        
        # Common patterns
        patterns = [
            r'experience\s+(?:in|with|of)\s+([^?]+)',
            r'years?\s+(?:of\s+)?(?:experience\s+)?(?:in|with|of)\s+([^?]+)',
            r'skill\s+(?:in|with|of)\s+([^?]+)',
            r'knowledge\s+(?:of|in|with)\s+([^?]+)',
            r'worked\s+with\s+([^?]+)',
            r'familiar\s+with\s+([^?]+)',
            r'proficient\s+in\s+([^?]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, q_lower)
            if match:
                skill = match.group(1).strip()
                # Clean up
                skill = re.sub(r'\s+(?:years?|yrs?|experience|\?).*$', '', skill).strip()
                # Remove common filler words at the end
                skill = re.sub(r'\s+(?:do|you|have|in|the|a|an)$', '', skill).strip()
                if len(skill) > 2:
                    return skill
        
        # Try to find known tech terms
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
        
        return None'''

new_fallback = '''    def _fallback_extract_skill(self, question: str) -> Optional[str]:
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
        # Common patterns: "experience in X", "years of experience in X", "skill in X", "knowledge of X"
        patterns = [
            r'(?:experience|years?)\s+(?:in|with|of)\s+([a-zA-Z0-9\s\+\#\.\-]{3,50}?)(?:\s+(?:years?|yrs?|\?|do|you|have|please|rate|your)|\s*$)',
            r'(?:skill|knowledge)\s+(?:in|with|of)\s+([a-zA-Z0-9\s\+\#\.\-]{3,50}?)(?:\s+(?:years?|yrs?|\?|do|you|have|please|rate|your)|\s*$)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, q_lower)
            if match:
                skill = match.group(1).strip()
                skill = re.sub(r'\s+(?:years?|yrs?|experience|\?|do|you|have|in|the|a|an|please|rate|your).*$', '', skill).strip()
                if len(skill) > 2:
                    return skill
        
        return None'''

with open('src/llm_extractor.py', 'r') as f:
    content = f.read()

if old in content:
    content = content.replace(old, new)
    with open('src/llm_extractor.py', 'w') as f:
        f.write(content)
    print("Updated _fallback_extract_skill method")
else:
    print("Could not find _fallback_extract_skill method")
    idx = content.find('def _fallback_extract_skill')
    if idx >= 0:
        print(f"Found at index {idx}")
        print(content[idx:idx+200])
PYEOF