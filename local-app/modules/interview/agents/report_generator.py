import os
import json
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Base path for session profile cache
SESSIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 
    "data", 
    "sessions"
)

class ReportGenerator:
    """
    Report Generation Agent. Aggregates candidate profile details, semantic matches,
    transcribed interview question histories, and sensor signals into a professional report.
    """

    def __init__(self):
        pass

    def _calculate_recommendations(self, match_results: Dict[str, Any], sub_scores: Dict[str, float]) -> Dict[str, Any]:
        """
        Calculate personalized, actionable coaching/learning recommendations based on the candidate's performance.
        """
        recommendations = {
            "technical_learning_paths": {},
            "communication_advice": None,
            "presentation_advice": [],
            "custom_practice_questions": []
        }
        
        # 1. Analyze skill gaps from match results
        skill_gaps = match_results.get("skill_gap", []) if match_results else []
        for gap in skill_gaps:
            recommendations["technical_learning_paths"][gap] = {
                "action_items": [
                    f"Read official documentation and explore advanced features of {gap}.",
                    f"Build a small end-to-end prototype using {gap} to gain hands-on proficiency.",
                    f"Review open-source examples showing {gap} integrated in real-world applications."
                ],
                "suggested_resources": [
                    f"Official {gap} Documentation",
                    f"Production-ready design patterns for {gap}",
                    f"Community forums and tutorials for {gap}"
                ]
            }
            # Custom practice questions based on identified gaps
            recommendations["custom_practice_questions"].append(
                f"How would you explain the architecture and key benefits of using {gap} in a production environment?"
            )
            recommendations["custom_practice_questions"].append(
                f"Describe a challenge you might face when integrating {gap} into an existing software stack, and how you would address it."
            )
            
        if not skill_gaps:
            recommendations["custom_practice_questions"].append(
                "Describe a complex technical challenge you solved recently and the trade-offs you considered."
            )
            
        # 2. Analyze communication quality
        comm_score = sub_scores.get("communication_quality", 70.0)
        if comm_score < 75.0:
            recommendations["communication_advice"] = (
                "Your communication score was below 75. We suggest using the STAR method "
                "(Situation, Task, Action, Result) to structure your behavioral responses. "
                "Furthermore, focus on explaining deeper trade-off rationales behind your technical decisions."
            )
            
        # 3. Analyze posture and eye contact
        posture_score = sub_scores.get("posture", 70.0)
        eye_score = sub_scores.get("eye_contact", 70.0)
        if posture_score < 75.0:
            recommendations["presentation_advice"].append(
                "Maintain correct posture alignment. Ensure you sit straight and keep your shoulders symmetrical."
            )
        if eye_score < 75.0:
            recommendations["presentation_advice"].append(
                "Keep a steady gaze on the camera rather than the screen to project direct eye contact with the interviewer."
            )
            
        return recommendations

    def generate_report(
        self,
        session_id: str,
        cand_profile: Optional[Dict[str, Any]] = None,
        match_results: Optional[Dict[str, Any]] = None,
        db_history: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Compiles the candidate interview history and generates a comprehensive evaluation report.
        Saves report to recruiter_report.json.
        """
        logger.info(f"Compiling final recruiter report for session {session_id}")
        sess_path = os.path.join(SESSIONS_DIR, session_id)
        
        # Load files if not provided in-memory
        if cand_profile is None:
            cand_profile = {}
            cand_path = os.path.join(sess_path, "candidate_profile.json")
            if os.path.exists(cand_path):
                with open(cand_path, "r", encoding="utf-8") as f:
                    cand_profile = json.load(f)
        
        if match_results is None:
            match_results = {}
            match_path = os.path.join(sess_path, "match_results.json")
            if os.path.exists(match_path):
                with open(match_path, "r", encoding="utf-8") as f:
                    match_results = json.load(f)

        if db_history is not None:
            history = db_history
        else:
            interview_state = {}
            state_path = os.path.join(sess_path, "interview_state.json")
            if os.path.exists(state_path):
                with open(state_path, "r", encoding="utf-8") as f:
                    interview_state = json.load(f)
            history = interview_state.get("history", [])

        # 1. Compute Sub-scores
        if history:
            def get_metric_score(h, key, default):
                val = h.get("metrics", {}).get(key, default)
                if isinstance(val, dict):
                    val = val.get("score", default)
                if isinstance(val, (int, float)):
                    if val <= 1.0:
                        return val * 100.0
                    return val
                return default

            tech_score = sum(h.get("technical_competency", h.get("accuracy_score", 70.0)) for h in history) / len(history)
            comm_score = sum(h.get("communication_quality", 70.0) for h in history) / len(history)
            behavioral_score = sum(h.get("behavioral_assessment", 70.0) for h in history) / len(history)
            learning_potential = sum(h.get("learning_potential") if h.get("learning_potential") is not None else 75.0 for h in history) / len(history)
            cultural_fit = sum(h.get("cultural_fit") if h.get("cultural_fit") is not None else 75.0 for h in history) / len(history)
            
            posture_score = sum(get_metric_score(h, "posture", 70.0) for h in history) / len(history)
            eye_score = sum(get_metric_score(h, "eye_contact", 70.0) for h in history) / len(history)
            body_score = sum(get_metric_score(h, "body_language", 70.0) for h in history) / len(history)
            attire_score = sum(get_metric_score(h, "attire", 70.0) for h in history) / len(history)
            presence_score = sum(get_metric_score(h, "professional_presence", 70.0) for h in history) / len(history)
        else:
            tech_score = 75.0
            comm_score = 75.0
            behavioral_score = 75.0
            learning_potential = 75.0
            cultural_fit = 75.0
            posture_score = 80.0
            eye_score = 80.0
            body_score = 80.0
            attire_score = 80.0
            presence_score = 80.0

        # Calculate Overall Score (weighted average)
        overall_score = round(
            (tech_score * 0.30) +
            (comm_score * 0.20) +
            (presence_score * 0.15) +
            (behavioral_score * 0.15) +
            (body_score * 0.10) +
            (attire_score * 0.10),
            1
        )

        # Retrieve resume-JD match rating and compute combined role alignment score
        resume_jd_score = match_results.get("role_alignment_score") if match_results else 75.0
        if resume_jd_score is None:
            resume_jd_score = 75.0
        role_alignment_score = round((resume_jd_score * 0.4) + (overall_score * 0.6), 1)

        # 2. Extract Behavioral / Emotional Summary
        emotions_encountered = set()
        for h in history:
            for emotion in h.get("metrics", {}).get("emotions", []):
                emotions_encountered.add(emotion.lower())
        
        if "nervous" in emotions_encountered or "anxious" in emotions_encountered:
            behavior_summary = "The candidate demonstrated initial nervous signals but remained composed and communicative throughout the session."
        else:
            behavior_summary = "The candidate maintained a professional, calm demeanor with highly stable engagement metrics."

        # 3. Assemble Strengths & Improvements
        strengths = list(match_results.get("strengths", []))
        strengths.append("Completed the full interview session.")
        if comm_score >= 80.0:
            strengths.append("Excellent communication skills with structured, detailed answers.")
        if posture_score >= 85.0:
            strengths.append("Very strong posture alignment and positive non-verbal cues.")
        if presence_score >= 85.0:
            strengths.append("Exceptional professional presence and composure.")

        improvements = []
        if match_results.get("skill_gap"):
            gaps = ", ".join(match_results.get("skill_gap"))
            improvements.append(f"Strengthen alignment on missing stack technologies: {gaps}.")
        if comm_score < 65.0:
            improvements.append("Elaborate further on engineering choices (answers were slightly brief).")
        if eye_score < 75.0:
            improvements.append("Maintain more direct camera gaze/eye contact during verbal explanations.")
        if posture_score < 75.0:
            improvements.append("Improve posture symmetry and try to avoid slouching.")

        # 4. Final report object
        report = {
            "session_id": session_id,
            "overall_score": overall_score,
            "role_alignment_score": role_alignment_score,
            "sub_scores": {
                "technical_competency": round(tech_score, 1),
                "communication_quality": round(comm_score, 1),
                "behavioral_assessment": round(behavioral_score, 1),
                "learning_potential": round(learning_potential, 1),
                "cultural_fit": round(cultural_fit, 1),
                "posture": round(posture_score, 1),
                "eye_contact": round(eye_score, 1),
                "body_language": round(body_score, 1),
                "attire": round(attire_score, 1),
                "professional_presence": round(presence_score, 1)
            },
            "candidate_recommendations": self._calculate_recommendations(match_results, {
                "technical_competency": tech_score,
                "communication_quality": comm_score,
                "behavioral_assessment": behavioral_score,
                "learning_potential": learning_potential,
                "cultural_fit": cultural_fit,
                "posture": posture_score,
                "eye_contact": eye_score,
                "body_language": body_score,
                "attire": attire_score,
                "professional_presence": presence_score
            }),
            "experience_years": cand_profile.get("experience", 0),
            "career_level": cand_profile.get("career_level", "Mid-level"),
            "specialization": cand_profile.get("specialization", []),
            "strengths": strengths,
            "areas_of_improvement": improvements,
            "behavior_summary": behavior_summary,
            "qa_history": history
        }

        # Save to recruiter_report.json
        report_path = os.path.join(sess_path, "recruiter_report.json")
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=4)

        logger.info(f"Saved recruiter report for session {session_id} to {report_path}")
        return report
