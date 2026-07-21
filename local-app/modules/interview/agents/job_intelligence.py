import os
import re
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# List of common security/injection phrases to sanitize (just in case candidates/users try injection in JD)
INJECTION_PATTERNS = [
    r"(?i)ignore\s+(?:all\s+)?previous\s+instructions",
    r"(?i)system\s+prompt\s+override",
    r"(?i)override\s+(?:all\s+)?settings",
]

class JobDescriptionIntelligenceAgent:
    """
    Parses and extracts expected requirements, responsibilities, skills, and organizational 
    expectations from a pasted job description or uploaded document to build a structured Role Profile.
    """

    def __init__(self):
        # Known technologies to map from job descriptions
        self.tech_keywords = [
            "python", "javascript", "typescript", "go", "golang", "java", "c++", "c#", "ruby", "rust", 
            "fastapi", "django", "flask", "react", "angular", "vue", "next.js", "express", 
            "docker", "kubernetes", "git", "aws", "gcp", "azure", "postgresql", "mysql", "mongodb", "redis",
            "sql", "html", "css", "machine learning", "pytorch", "tensorflow", "ci/cd", "rest api", "graphql"
        ]

    def sanitize_text(self, text: str) -> str:
        if not text:
            return ""
        clean = re.sub(r"<[^>]*>", " ", text)
        for pattern in INJECTION_PATTERNS:
            clean = re.sub(pattern, "[Sanitized Malicious Intent Phrase]", clean)
        clean = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", clean)
        clean = re.sub(r"\s+", " ", clean)
        return clean.strip()

    def parse_file(self, file_path: str) -> str:
        """Parses text from PDF, DOCX, or TXT format safely."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Job description file not found: {file_path}")

        _, ext = os.path.splitext(file_path.lower())
        raw_text = ""

        try:
            if ext == ".pdf":
                from pypdf import PdfReader
                reader = PdfReader(file_path)
                pages_text = []
                for page in reader.pages[:10]:
                    txt = page.extract_text()
                    if txt:
                        pages_text.append(txt)
                raw_text = "\n".join(pages_text)

            elif ext == ".docx":
                import docx
                doc = docx.Document(file_path)
                paragraphs = [p.text for p in doc.paragraphs[:500] if p.text]
                raw_text = "\n".join(paragraphs)

            else:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    raw_text = f.read(100000)

            return self.sanitize_text(raw_text)

        except Exception as e:
            logger.error(f"Error parsing job description file {file_path}: {e}")
            raise ValueError(f"Failed to read job description file: {str(e)}")

    def extract_required_experience(self, text: str) -> int:
        """
        Extracts expected minimum years of experience.
        """
        # Matches e.g., "5+ years of experience", "minimum 3 years", "8 years", "5-7 years"
        match = re.search(r"(?:minimum|min|at least|required)?\s*(\d+)\+?\s*(?:-\s*\d+)?\s*years?(?:\s+of)?\s*(?:relevant)?\s*experience", text, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return 2  # default baseline if unspecified

    def extract_role_profile(self, text: str) -> Dict[str, Any]:
        """
        Builds a structured Role Profile from JD text.
        """
        sanitized = self.sanitize_text(text)
        profile = {
            "required_skills": [],
            "required_experience_years": 2,
            "responsibilities": [],
            "preferred_qualifications": [],
            "soft_skills": [],
            "industry_domain": "Software Development",
        }

        # 1. Required Experience
        profile["required_experience_years"] = self.extract_required_experience(sanitized)

        # 2. Required Skills (Word matching from technical dictionary)
        for skill in self.tech_keywords:
            pattern = rf"(?i)\b{re.escape(skill)}\b"
            if re.search(pattern, sanitized):
                name = skill.replace("\\", "").title()
                if name.lower() == "gcp": name = "GCP"
                elif name.lower() == "aws": name = "AWS"
                elif name.lower() == "html": name = "HTML"
                elif name.lower() == "css": name = "CSS"
                elif name.lower() == "sql": name = "SQL"
                elif name.lower() == "ci/cd": name = "CI/CD"
                elif name.lower() == "rest api": name = "REST API"
                profile["required_skills"].append(name)

        # 3. Soft Skills
        soft_skills_list = ["communication", "collaboration", "leadership", "adaptability", "team player", "agile", "scrum", "mentoring"]
        for skill in soft_skills_list:
            if re.search(rf"(?i)\b{re.escape(skill)}\b", sanitized):
                profile["soft_skills"].append(skill.title())

        # 4. Parsing Responsibilities & Qualifications from text sections
        lines = text.split("\n")
        current_section = None
        buffers = {
            "responsibilities": [],
            "preferred": [],
        }

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            lower_line = line_str.lower()
            if any(k in lower_line for k in ["responsibilities", "what you will do", "duties", "role description"]):
                current_section = "responsibilities"
                continue
            elif any(k in lower_line for k in ["preferred", "nice to have", "plus", "bonus", "qualifications", "requirements"]):
                # if section contains qualifications, but if it has preferred/plus/bonus we classify it as preferred
                if any(p in lower_line for p in ["preferred", "nice to have", "plus", "bonus"]):
                    current_section = "preferred"
                else:
                    current_section = "requirements" # general requirements section
                continue

            if current_section == "responsibilities" and len(buffers["responsibilities"]) < 10:
                buffers["responsibilities"].append(line_str)
            elif current_section == "preferred" and len(buffers["preferred"]) < 8:
                buffers["preferred"].append(line_str)

        # Populate responsibilities
        for line in buffers["responsibilities"]:
            if line.startswith(("-", "*", "•")) or len(line) < 120:
                profile["responsibilities"].append(line.lstrip("-*• ").strip())

        # Populate preferred qualifications
        for line in buffers["preferred"]:
            if line.startswith(("-", "*", "•")) or len(line) < 120:
                profile["preferred_qualifications"].append(line.lstrip("-*• ").strip())

        # If buffers are empty, extract lines with action verbs as default responsibilities
        if not profile["responsibilities"]:
            action_verbs = ["design", "develop", "maintain", "build", "collaborate", "lead", "manage", "optimize", "write"]
            for line in lines[:30]:
                if any(line.strip().lower().startswith(v) for v in action_verbs):
                    profile["responsibilities"].append(line.strip())

        # Determine Industry Domain
        if any(w in sanitized.lower() for w in ["ai", "machine learning", "pytorch", "model"]):
            profile["industry_domain"] = "Artificial Intelligence"
        elif any(w in sanitized.lower() for w in ["cloud", "devops", "aws", "kubernetes"]):
            profile["industry_domain"] = "Cloud & Infrastructure"
        elif any(w in sanitized.lower() for w in ["finance", "banking", "payment", "ledger"]):
            profile["industry_domain"] = "FinTech"
        elif any(w in sanitized.lower() for w in ["healthcare", "medical", "patient", "clinical"]):
            profile["industry_domain"] = "HealthTech"

        return profile
