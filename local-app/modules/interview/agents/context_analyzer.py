import os
import json
import logging
from typing import Dict, Any, Optional

from .resume_intelligence import ResumeIntelligenceAgent
from .job_intelligence import JobDescriptionIntelligenceAgent
from .matching_engine import MatchingEngine

logger = logging.getLogger(__name__)

# Base path for session profile cache
SESSIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 
    "data", 
    "sessions"
)

class ContextAnalyzer:
    """
    Orchestrator for candidate context. Processes uploaded resumes and job descriptions,
    saves profiles to session directories, and evaluates semantic matching and skill gaps.
    """

    def __init__(self):
        self.resume_agent = ResumeIntelligenceAgent()
        self.jd_agent = JobDescriptionIntelligenceAgent()
        self.matching_engine = MatchingEngine()

    def _ensure_session_dir(self, session_id: str) -> str:
        sess_path = os.path.join(SESSIONS_DIR, session_id)
        os.makedirs(sess_path, exist_ok=True)
        return sess_path

    def get_session_profile(self, session_id: str) -> Dict[str, Any]:
        """
        Loads the candidate profile, role profile, and match results for a session if they exist.
        """
        sess_path = os.path.join(SESSIONS_DIR, session_id)
        
        # Load normalized candidate profile if exists, else fallback to raw resume profile
        normalized_cand_path = os.path.join(sess_path, "candidate_profile.json")
        cand_path = os.path.join(sess_path, "resume_profile.json")
        role_path = os.path.join(sess_path, "jd_profile.json")
        match_path = os.path.join(sess_path, "match_results.json")

        cand_profile = None
        role_profile = None
        match_results = None

        if os.path.exists(normalized_cand_path):
            with open(normalized_cand_path, "r", encoding="utf-8") as f:
                cand_profile = json.load(f)
        elif os.path.exists(cand_path):
            with open(cand_path, "r", encoding="utf-8") as f:
                cand_profile = json.load(f)
        
        if os.path.exists(role_path):
            with open(role_path, "r", encoding="utf-8") as f:
                role_profile = json.load(f)

        if os.path.exists(match_path):
            with open(match_path, "r", encoding="utf-8") as f:
                match_results = json.load(f)

        return {
            "session_id": session_id,
            "has_resume": cand_profile is not None,
            "has_jd": role_profile is not None,
            "candidate_profile": cand_profile,
            "role_profile": role_profile,
            "match_results": match_results
        }

    async def parse_and_save_resume(self, session_id: str, file_path: str) -> Dict[str, Any]:
        """
        Extracts structured text from a resume file, runs the extraction agent,
        and saves candidate_profile to disk. Recalculates match alignment if JD is present.
        """
        logger.info(f"Parsing resume for session {session_id} from {file_path}")
        raw_text = self.resume_agent.parse_file(file_path)
        cand_profile = self.resume_agent.extract_profile(raw_text)
        
        # Save to session directory
        sess_path = self._ensure_session_dir(session_id)
        cand_path = os.path.join(sess_path, "resume_profile.json")
        with open(cand_path, "w", encoding="utf-8") as f:
            json.dump(cand_profile, f, indent=4)

        # Trigger re-matching if JD already exists
        role_path = os.path.join(sess_path, "jd_profile.json")
        if os.path.exists(role_path):
            with open(role_path, "r", encoding="utf-8") as f:
                role_profile = json.load(f)
            self._run_matching(session_id, cand_profile, role_profile)

        return cand_profile

    async def parse_and_save_jd(self, session_id: str, text: str = "", file_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Extracts structured text from a job description string or file, runs the extraction agent,
        and saves role_profile to disk. Recalculates match alignment if resume is present.
        """
        logger.info(f"Parsing job description for session {session_id}")
        raw_text = ""
        if file_path:
            raw_text = self.jd_agent.parse_file(file_path)
        elif text:
            raw_text = self.jd_agent.sanitize_text(text)
        else:
            raise ValueError("Must provide either JD text or file_path")

        role_profile = self.jd_agent.extract_role_profile(raw_text)

        # Save to session directory
        sess_path = self._ensure_session_dir(session_id)
        role_path = os.path.join(sess_path, "jd_profile.json")
        with open(role_path, "w", encoding="utf-8") as f:
            json.dump(role_profile, f, indent=4)

        # Trigger re-matching if resume already exists
        cand_path = os.path.join(sess_path, "resume_profile.json")
        if os.path.exists(cand_path):
            with open(cand_path, "r", encoding="utf-8") as f:
                cand_profile = json.load(f)
            self._run_matching(session_id, cand_profile, role_profile)

        return role_profile

    def _run_matching(self, session_id: str, cand_profile: Dict[str, Any], role_profile: Dict[str, Any]) -> Dict[str, Any]:
        """
        Runs the semantic matching engine, generates the normalized candidate profile,
        and saves all alignment/profile data to disk.
        """
        logger.info(f"Running profile matching alignment for session {session_id}")
        match_results = self.matching_engine.align_profiles(cand_profile, role_profile)
        
        sess_path = self._ensure_session_dir(session_id)
        
        # Save raw matching engine output
        match_path = os.path.join(sess_path, "match_results.json")
        with open(match_path, "w", encoding="utf-8") as f:
            json.dump(match_results, f, indent=4)

        # Generate normalized Candidate Profile (Feature 6)
        cand_exp = cand_profile.get("experience_years", 0)
        if cand_exp < 2:
            career_level = "Junior / Entry-level"
        elif cand_exp <= 5:
            career_level = "Mid-level"
        else:
            career_level = "Senior / Lead"

        specialization = cand_profile.get("domain_expertise", ["Generalist"])

        compiled_profile = {
            "skills": cand_profile.get("skills", {}),
            "experience": cand_exp,
            "education": cand_profile.get("education", []),
            "project_expertise": cand_profile.get("projects", []),
            "specialization": specialization,
            "strengths": match_results.get("strengths", []),
            "likely_weaknesses": match_results.get("weaknesses", []),
            "career_level": career_level,
            "interview_focus_areas": match_results.get("skill_gap", []),
        }

        # Save normalized Candidate Profile
        cand_prof_path = os.path.join(sess_path, "candidate_profile.json")
        with open(cand_prof_path, "w", encoding="utf-8") as f:
            json.dump(compiled_profile, f, indent=4)

        logger.info(f"Compiled and saved normalized Candidate Profile for session {session_id}")
        return match_results
