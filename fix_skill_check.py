with open('src/chatbot_answerer.py', 'r') as f:
    content = f.read()

old = """    def _is_skill_known(self, skill_lower: str) -> bool:
        """Check if skill exists in our inventory (exact or fuzzy match)."""
        # Direct match
        if skill_lower in self.skill_inventory:
            return True
        
        # Fuzzy match against known skills
        if RAPIDFUZZ_AVAILABLE:
            from rapidfuzz import process
            match = process.extractOne(skill_lower, self.skill_inventory.keys(), score_cutoff=85)
            if match:
                return True
        
        # Check aliases
        skill_aliases = {
            "azure cloud": "azure",
            "aws cloud": "aws", 
            "google cloud": "gcp",
            "gcp": "google cloud",
            "k8s": "kubernetes",
            "ci cd": "ci/cd",
            "cicd": "ci/cd",
            "infra as code": "infrastructure as code",
            "iac": "infrastructure as code",
        }
        
        for alias, canonical in skill_aliases.items():
            if alias in skill_lower and canonical in self.skill_inventory:
                return True
        
        return False"""

new = """    def _is_skill_known(self, skill_lower: str) -> bool:
        """Check if skill exists in our inventory (exact or fuzzy match)."""
        # Direct match
        if skill_lower in self.skill_inventory:
            return True
        
        # Also check optimized_skills from profile
        if skill_lower in self.optimized_skills:
            return True
        
        # Fuzzy match against known skills
        if RAPIDFUZZ_AVAILABLE:
            from rapidfuzz import process
            match = process.extractOne(skill_lower, self.skill_inventory.keys(), score_cutoff=85)
            if match:
                return True
            # Also check optimized_skills
            match = process.extractOne(skill_lower, self.optimized_skills.keys(), score_cutoff=85)
            if match:
                return True
        
        # Check aliases
        skill_aliases = {
            "azure cloud": "azure",
            "aws cloud": "aws", 
            "google cloud": "gcp",
            "gcp": "google cloud",
            "k8s": "kubernetes",
            "ci cd": "ci/cd",
            "cicd": "ci/cd",
            "infra as code": "infrastructure as code",
            "iac": "infrastructure as code",
        }
        
        for alias, canonical in skill_aliases.items():
            if alias in skill_lower and canonical in self.skill_inventory:
                return True
            if alias in skill_lower and canonical in self.optimized_skills:
                return True
        
        return False"""

with open('src/chatbot_answerer.py', 'r') as f:
    content = f.read()

if old in content:
    content = content.replace(old, new)
    with open('src/chatbot_answerer.py', 'w') as f:
        f.write(content)
    print("Updated _is_skill_known method")
else:
    print("Could not find _is_skill_known method")
    idx = content.find('def _is_skill_known')
    if idx >= 0:
        print(f"Found at index {idx}")
        print(content[idx:idx+200])
