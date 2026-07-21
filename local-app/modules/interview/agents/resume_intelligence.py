import os
import re
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# List of common security/injection phrases to sanitize
INJECTION_PATTERNS = [
    r"(?i)ignore\s+(?:all\s+)?previous\s+instructions",
    r"(?i)system\s+prompt\s+override",
    r"(?i)override\s+(?:all\s+)?settings",
    r"(?i)you\s+must\s+score\s+(?:this\s+candidate\s+)?100",
    r"(?i)ignore\s+constraints",
    r"(?i)bypass\s+evaluation",
    r"(?i)ignore\s+posture\s+and\s+eye\s+contact",
]

class ResumeIntelligenceAgent:
    """
    Parses and sanitizes resumes (PDF, DOCX, TXT) and extracts a structured Candidate Profile
    using deterministic NLP, keyword associations, and context-based proficiency estimators.
    """

    def __init__(self):
        # Compiled regexes for skill categorization
        self.skills_db = {
            "programming_languages": ["python", "javascript", "typescript", "go", "golang", "java", "c++", "c#", "ruby", "rust", "php", "swift", "kotlin", "sql", "html", "css"],
            "frameworks": ["fastapi", "django", "flask", "react", "angular", "vue", "next.js", "express", "spring boot", "laravel", "rails", "nestjs", "pytorch", "tensorflow"],
            "tools_databases": ["docker", "kubernetes", "git", "aws", "gcp", "azure", "postgresql", "mysql", "mongodb", "redis", "sqlite", "elasticsearch", "nginx", "jenkins"],
            "soft_skills": ["communication", "teamwork", "leadership", "problem-solving", "collaboration", "adaptability", "mentorship", "critical thinking"],
        }

    def sanitize_text(self, text: str) -> str:
        """
        Cleans text and neutralizes prompt injections, script tags, or malicious commands.
        """
        if not text:
            return ""
        
        # Remove HTML/XML tags
        clean = re.sub(r"<[^>]*>", " ", text)
        
        # Neutralize malicious instructions
        for pattern in INJECTION_PATTERNS:
            clean = re.sub(pattern, "[Sanitized Malicious Intent Phrase]", clean)
            
        # Strip suspicious terminal escape sequences or weird control chars
        clean = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", clean)
        
        # Normalize whitespace
        clean = re.sub(r"\s+", " ", clean)
        return clean.strip()

    def parse_file(self, file_path: str) -> str:
        """
        Parses text from PDF, DOCX, or TXT format safely.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Resume file not found: {file_path}")

        _, ext = os.path.splitext(file_path.lower())
        raw_text = ""

        try:
            if ext == ".pdf":
                from pypdf import PdfReader
                reader = PdfReader(file_path)
                pages_text = []
                # Restrict to first 10 pages to avoid decompression bomb/infinite loops
                for page in reader.pages[:10]:
                    txt = page.extract_text()
                    if txt:
                        pages_text.append(txt)
                raw_text = "\n".join(pages_text)

            elif ext == ".docx":
                import docx
                doc = docx.Document(file_path)
                # Safeguard against huge files (max 500 paragraphs)
                paragraphs = [p.text for p in doc.paragraphs[:500] if p.text]
                raw_text = "\n".join(paragraphs)

            else:
                # Default to plain text
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    raw_text = f.read(100000) # Max 100KB read limit for protection

            return self.sanitize_text(raw_text)

        except Exception as e:
            logger.error(f"Error parsing resume file {file_path}: {e}")
            raise ValueError(f"Failed to read resume file: {str(e)}")

    def extract_experience_years(self, text: str) -> int:
        """
        Estimates total years of experience from years and date ranges.
        """
        # Look for explicit mentions like "5 years of experience", "10+ years"
        exp_match = re.search(r"(\d+)\+?\s*years?\s+(?:of\s+)?experience", text, re.IGNORECASE)
        if exp_match:
            return int(exp_match.group(1))
            
        # Parse date ranges (e.g. 2018 - 2023 or 2019-Present)
        years = re.findall(r"\b(20\d{2})\s*[-–—]\s*(Present|20\d{2})\b", text, re.IGNORECASE)
        total_years = 0
        current_year = 2026 # Context local year is 2026
        for start, end in years:
            try:
                sy = int(start)
                ey = current_year if end.lower() == "present" else int(end)
                if ey >= sy:
                    total_years += (ey - sy)
            except Exception:
                continue
        return max(1, total_years) if total_years > 0 else 2 # default to 2 years baseline if undetermined

    def estimate_proficiency(self, skill: str, text: str, total_years: int) -> str:
        """
        Determines proficiency level based on proximity of skill to expertise keywords,
        mentions in work experience, and overall career level.
        """
        skill_escaped = re.escape(skill)
        # Search for senior expertise keywords within 40 characters of the skill
        expert_pattern = rf"(?i)(?:expert|lead|senior|principal|architect|advanced|proficient)\s*.{{0,40}}{skill_escaped}|{skill_escaped}\s*.{{0,40}}(?:expert|lead|senior|principal|architect|advanced|proficient)"
        if re.search(expert_pattern, text):
            return "Advanced"
            
        # Beginner keywords
        beginner_pattern = rf"(?i)(?:beginner|entry|junior|learning|basic|familiar)\s*.{{0,40}}{skill_escaped}|{skill_escaped}\s*.{{0,40}}(?:beginner|entry|junior|learning|basic|familiar)"
        if re.search(beginner_pattern, text):
            return "Beginner"
            
        # If total experience is > 6 years and skill matches multiple locations (highly used), call it Advanced
        skill_occurrences = len(re.findall(rf"(?i)\b{skill_escaped}\b", text))
        if total_years >= 6 and skill_occurrences > 2:
            return "Advanced"
        elif total_years <= 2 or skill_occurrences == 1:
            return "Beginner"
            
        return "Intermediate"

    def extract_profile(self, text: str) -> Dict[str, Any]:
        """
        Extracts structured education, experience, skills, projects, and domain expertise.
        """
        profile = {
            "skills": {},
            "education": [],
            "certifications": [],
            "experience_years": 0,
            "projects": [],
            "achievements": [],
            "work_history": [],
            "domain_expertise": [],
        }

        # 1. Total Experience
        total_years = self.extract_experience_years(text)
        profile["experience_years"] = total_years

        # 2. Skill Extraction & Proficiency Mapping
        for category, list_of_skills in self.skills_db.items():
            profile["skills"][category] = []
            for skill in list_of_skills:
                # Word boundary match
                pattern = rf"(?i)\b{re.escape(skill)}\b"
                if re.search(pattern, text):
                    prof = self.estimate_proficiency(skill, text, total_years)
                    # format display name nicely
                    name = skill.replace("\\", "").title()
                    if name.lower() == "gcp": name = "GCP"
                    elif name.lower() == "aws": name = "AWS"
                    elif name.lower() == "html": name = "HTML"
                    elif name.lower() == "css": name = "CSS"
                    elif name.lower() == "sql": name = "SQL"
                    profile["skills"][category].append({"name": name, "level": prof})

        # 3. Parse Sections via Heuristic Keywords
        lines = text.split("\n")
        current_section = None
        section_buffers = {
            "education": [],
            "experience": [],
            "projects": [],
            "certifications": [],
        }

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue
            
            # Detect section transitions
            lower_line = line_str.lower()
            if any(k in lower_line for k in ["education", "academic", "university", "college"]):
                current_section = "education"
                continue
            elif any(k in lower_line for k in ["experience", "employment", "work history", "professional history"]):
                current_section = "experience"
                continue
            elif any(k in lower_line for k in ["projects", "personal projects", "open source"]):
                current_section = "projects"
                continue
            elif any(k in lower_line for k in ["certification", "certificates", "credentials"]):
                current_section = "certifications"
                continue

            if current_section and len(section_buffers[current_section]) < 15: # Limit rows per section
                section_buffers[current_section].append(line_str)

        # Process Education
        for line in section_buffers["education"]:
            if any(deg in line.lower() for deg in ["bachelor", "master", "phd", "b.s", "m.s", "b.tech", "m.tech", "degree"]):
                profile["education"].append(line)

        # Process Certifications
        for line in section_buffers["certifications"]:
            if any(cert in line.lower() for cert in ["aws", "certified", "google", "oracle", "scrum", "pmp", "cisco"]):
                profile["certifications"].append(line)

        # Process Projects
        for line in section_buffers["projects"]:
            # If line represents a title or bullet list description of project
            if line.startswith(("-", "*", "•")) or len(line) < 80:
                profile["projects"].append(line.lstrip("-*• ").strip())

        # Process Experience/Work History
        for line in section_buffers["experience"]:
            if len(line) > 10:
                profile["work_history"].append(line)

        # Determine Domain Expertise
        if any(w in text.lower() for w in ["backend", "api", "database", "fastapi"]):
            profile["domain_expertise"].append("Backend Engineering")
        if any(w in text.lower() for w in ["frontend", "react", "ui", "ux"]):
            profile["domain_expertise"].append("Frontend Development")
        if any(w in text.lower() for w in ["devops", "kubernetes", "docker", "cloud", "aws"]):
            profile["domain_expertise"].append("Cloud & DevOps")
        if any(w in text.lower() for w in ["machine learning", "pytorch", "tensorflow", "dataset", "ai"]):
            profile["domain_expertise"].append("AI / Machine Learning")

        return profile
