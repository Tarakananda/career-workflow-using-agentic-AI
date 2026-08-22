"""
Enhanced Skill Matcher with LLM-based Must-Have/Good-to-Have Extraction
"""
import re
import json
from typing import Optional, Dict, List, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum

# Import existing skill categories for fallback
from src.matcher_v2 import SKILL_CATEGORIES, SkillCategory, normalize_skill, extract_skills_from_text


class SkillRequirement(Enum):
    MUST_HAVE = "must_have"
    GOOD_TO_HAVE = "good_to_have"
    UNKNOWN = "unknown"


@dataclass
class ExtractedSkill:
    name: str
    requirement: SkillRequirement
    confidence: float
    category: Optional[str] = None
    evidence: str = ""


@dataclass
class JobRequirements:
    must_have: List[ExtractedSkill] = field(default_factory=list)
    good_to_have: List[ExtractedSkill] = field(default_factory=list)
    raw_text: str = ""
    
    @property
    def must_have_names(self) -> Set[str]:
        return {normalize_skill(s.name) for s in self.must_have}
    
    @property
    def good_to_have_names(self) -> Set[str]:
        return {normalize_skill(s.name) for s in self.good_to_have}
    
    @property
    def all_names(self) -> Set[str]:
        return self.must_have_names | self.good_to_have_names


class LLMSkillExtractor:
    """Extract must-have and good-to-have skills from job descriptions using LLM."""
    
    SYSTEM_PROMPT = """You are an expert at analyzing job descriptions for technical roles.
Extract all technical skills mentioned and classify them as MUST_HAVE (required/essential) or GOOD_TO_HAVE (preferred/nice-to-have).

Rules:
1. MUST_HAVE: Skills explicitly required, mandatory, essential, "must have", "required", "expertise in", "proficient in", "deep experience with"
2. GOOD_TO_HAVE: Skills mentioned as "preferred", "nice to have", "plus", "bonus", "familiarity with", "exposure to", "knowledge of", "plus if"
3. If unclear, default to GOOD_TO_HAVE
4. Include: programming languages, cloud platforms, tools, frameworks, databases, methodologies, certifications
5. Normalize skill names (lowercase, standardize: "k8s"->"kubernetes", "aws cloud"->"aws", etc.)

Output JSON format:
{
  "skills": [
    {"name": "skill_name", "requirement": "must_have|good_to_have", "confidence": 0.9, "category": "cloud|database|language|tool|framework|etc", "evidence": "quote from job description"}
  ]
}"""

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        self.model = model
        try:
            from openai import OpenAI
            self.client = OpenAI(api_key=api_key) if api_key else OpenAI()
            self.available = True
        except Exception as e:
            print(f"OpenAI client not available: {e}")
            self.client = None
            self.available = False
    
    def extract_requirements(self, job_description: str) -> Dict:
        """Extract structured skill requirements from job description."""
        if not self.available or not self.client:
            fallback_result = self._fallback_extract(job_description)
            return self._process_llm_result(fallback_result)
        
        try:
            prompt = f"{self.SYSTEM_PROMPT}\n\nJob Description:\n{job_description[:15000]}"
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": f"Job Description:\n{job_description[:15000]}"}
                ],
                temperature=0.1,
                max_tokens=3000,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            return self._process_llm_result(result)
            
        except Exception as e:
            print(f"LLM extraction failed: {e}")
            return self._fallback_extract(job_description)
    
    def _fallback_extract(self, job_description: str) -> Dict:
        """Regex-based fallback extraction."""
        from src.matcher_v2 import extract_skills_from_text, SKILL_ALIASES, normalize_skill
        from src.matcher_v2 import SKILL_CATEGORIES
        
        text_lower = job_description.lower()
        found = set()
        
        # Get all known skills
        all_skills = set()
        for cat in SKILL_CATEGORIES:
            all_skills.update(cat.skills)
        
        # Check for explicit must-have patterns
        must_have_patterns = [
            r'(?:must\s+have|required|essential|mandatory|proficient\s+in|expertise\s+in|deep\s+experience\s+(?:in|with)|experience\s+in)\s+([^.\n]+)',
            r'(?:required|must-have)\s+skills?\s*:?\s*([^.\n]+)',
        ]
        
        good_to_have_patterns = [
            r'(?:preferred|nice\s+to\s+have|plus|bonus|familiar\s+with|exposure\s+to|knowledge\s+of)[:]?\s*([^.\n]+)',
            r'(?:nice\s+to\s+have|good\s+to\s+have|plus)\s*:?\s*([^.\n]+)',
        ]
        
        must_have = set()
        good_to_have = set()
        
        # Extract from explicit patterns
        for pattern in must_have_patterns:
            for match in re.finditer(pattern, job_description, re.IGNORECASE):
                skills_text = match.group(1)
                for skill in self._split_skills(skills_text):
                    norm_skill = normalize_skill(skill)
                    found.add(norm_skill)
                    must_have.add(norm_skill)
        
        for pattern in good_to_have_patterns:
            for match in re.finditer(pattern, job_description, re.IGNORECASE):
                skills_text = match.group(1)
                for skill in self._split_skills(skills_text):
                    norm_skill = normalize_skill(skill)
                    if norm_skill not in found:
                        good_to_have.add(norm_skill)
                    found.add(norm_skill)
        
        # Also find all known skills in text - treat as must_have by default
        # unless found in good_to_have patterns
        text_lower = job_description.lower()
        for skill in all_skills:
            if skill in job_description.lower():
                if skill not in found and skill not in good_to_have:
                    must_have.add(normalize_skill(skill))
        
        return {
            "skills": [
                {"name": s, "requirement": "must_have", "confidence": 0.8, "category": self._guess_category(s), "evidence": ""}
                for s in sorted(must_have)
            ] + [
                {"name": s, "requirement": "good_to_have", "confidence": 0.6, "category": self._guess_category(s), "evidence": ""}
                for s in sorted(good_to_have)
            ]
        }
    
    def _split_skills(self, text: str) -> List[str]:
        # Split by common delimiters (but not / to preserve ci/cd, etc.)
        parts = re.split(r'[,;|\n]', text)
        return [p.strip() for p in parts if p.strip() and len(p.strip()) > 1]
    
    def _guess_category(self, skill: str) -> str:
        for cat in SKILL_CATEGORIES:
            if skill in cat.skills:
                return cat.name
        return "unknown"
    
    def _process_llm_result(self, result: Dict) -> Dict:
        """Process LLM result into structured format."""
        must_have = []
        good_to_have = []
        
        for skill_data in result.get("skills", []):
            name = skill_data.get("name", "").strip().lower()
            req = skill_data.get("requirement", "good_to_have")
            conf = skill_data.get("confidence", 0.7)
            cat = skill_data.get("category", "unknown")
            evidence = skill_data.get("evidence", "")
            
            if not name:
                continue
            
            skill_obj = ExtractedSkill(
                name=name,
                requirement=SkillRequirement(req) if req in ["must_have", "good_to_have"] else SkillRequirement.UNKNOWN,
                confidence=conf,
                category=cat,
                evidence=evidence
            )
            
            if req == "must_have":
                must_have.append(skill_obj)
            else:
                good_to_have.append(skill_obj)
        
        return {
            "must_have": must_have,
            "good_to_have": good_to_have
        }


class ImprovedJobMatcher:
    """Enhanced job matcher with must-have/good-to-have awareness."""
    
    def __init__(self, llm_extractor: Optional[LLMSkillExtractor] = None):
        self.llm_extractor = llm_extractor or LLMSkillExtractor()
    
    def analyze_job(self, job_description: str, resume_skills: List[str]) -> Dict:
        """Analyze job against resume with must-have/good-to-have awareness."""
        # Extract job requirements
        req_data = self.llm_extractor.extract_requirements(job_description)
        
        must_have_names = set(s.name for s in req_data.get("must_have", []))
        good_to_have_names = set(s.name for s in req_data.get("good_to_have", []))
        all_job_skills = must_have_names | good_to_have_names
        
        resume_set = set(normalize_skill(s) for s in resume_skills)
        
        # Calculate match
        must_have_matched = must_have_names & resume_set
        must_have_missing = must_have_names - resume_set
        good_to_have_matched = good_to_have_names & resume_set
        good_to_have_missing = good_to_have_names - resume_set
        
        # Calculate scores
        must_have_total = len(must_have_names) if must_have_names else 1
        must_have_score = len(must_have_matched) / must_have_total * 100
        
        good_to_have_total = len(good_to_have_names) if good_to_have_names else 0
        good_to_have_score = len(good_to_have_matched) / good_to_have_total * 100 if good_to_have_total > 0 else 0
        
        # Overall score: weight based on what categories exist
        if good_to_have_total > 0:
            # Both categories exist: 70% must-have, 30% good-to-have
            overall_score = 0.7 * must_have_score + 0.3 * good_to_have_score
        else:
            # Only must-have skills: overall score = must-have score
            overall_score = must_have_score
        
        # Must-have requirement: at least 70% of must-have skills
        must_have_threshold = 70
        meets_must_have = must_have_score >= must_have_threshold
        
        # Pass if must-have requirement is met AND:
        # - No good-to-have skills in job, OR
        # - Must-have score is high enough (90%+), OR
        # - Overall score meets threshold
        if meets_must_have and (good_to_have_total == 0 or must_have_score >= 90 or overall_score >= 75):
            meets_threshold = True
        else:
            meets_threshold = False
        
        return {
            "overall_score": overall_score,
            "must_have_score": must_have_score,
            "good_to_have_score": good_to_have_score,
            "meets_must_have": meets_must_have,
            "must_have_matched": list(must_have_matched),
            "must_have_missing": list(must_have_missing),
            "good_to_have_matched": list(good_to_have_matched),
            "good_to_have_missing": list(good_to_have_missing),
            "must_have_total": len(must_have_names),
            "good_to_have_total": len(good_to_have_names),
            "meets_threshold": meets_threshold
        }


def create_improved_matcher(api_key: Optional[str] = None) -> ImprovedJobMatcher:
    """Factory function to create improved matcher."""
    llm_extractor = LLMSkillExtractor(api_key=api_key)
    return ImprovedJobMatcher(llm_extractor=llm_extractor)


# For backward compatibility
def should_apply_improved(resume_skills: List[str], job_description: str, threshold: float = 75.0) -> Tuple[bool, float, List[str], List[str]]:
    """Improved version of should_apply with must-have/good-to-have logic."""
    matcher = create_improved_matcher()
    result = matcher.analyze_job(job_description, resume_skills)
    
    matched = list(result.get("must_have_matched", set())) + list(result.get("good_to_have_matched", set()))
    missing = list(result.get("must_have_missing", set())) + list(result.get("good_to_have_missing", set()))
    
    return result["meets_threshold"], result["overall_score"], matched, missing


if __name__ == "__main__":
    # Test
    from src.matcher_v2 import SKILL_CATEGORIES
    
    test_job = """
    We are looking for a Power BI Developer with expertise in:
    - Must have: Power BI, DAX, Power Query, Microsoft Fabric, Data Modeling, ETL
    - Databases: SQL Server, PostgreSQL
    - Preferred: PySpark, Microsoft Fabric, Azure Functions
    - Cloud: Azure
    - Programming: Python
    """
    
    resume = ["python", "azure", "go", "docker", "kubernetes", "terraform", "aws", "gcp"]
    
    should, pct, matched, missing = should_apply_improved(resume, test_job, 75.0)
    print(f"Should apply: {should}")
    print(f"Match: {pct:.1f}%")
    print(f"Matched: {matched}")
    print(f"Missing: {missing}")