import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class ProfessionalPresenceEvaluator:
    """
    Composite evaluator that scores the candidate's professional presence.
    Combines posture alignment, attire formality/professionalism,
    gaze poise (eye contact), and facial composure.
    """

    def calculate(
        self,
        posture: Dict[str, Any],
        attire: Dict[str, Any],
        eye_contact: Dict[str, Any],
        facial_expression: Dict[str, Any]
    ) -> Dict[str, Any]:
        p_score = posture.get("score", 70.0)
        a_score = attire.get("score", 70.0)
        e_score = eye_contact.get("score", 70.0)

        # Facial composure: high nervous/confused values reduce composure
        face_details = facial_expression.get("details", {})
        if face_details.get("detected") and not face_details.get("mock"):
            scores = face_details.get("scores", {})
            nervous = scores.get("nervous", 0.0)
            confused = scores.get("confused", 0.0)
            composure_score = max(0.0, min(100.0, 100.0 - (nervous * 50.0 + confused * 30.0)))
        else:
            composure_score = facial_expression.get("score", 70.0)

        # Weighted calculation
        presence_score = (
            (p_score * 0.30) +
            (a_score * 0.20) +
            (e_score * 0.30) +
            (composure_score * 0.20)
        )

        return {
            "sensor_type": "professional_presence",
            "score": round(presence_score, 1),
            "details": {
                "posture_contribution": round(p_score, 1),
                "attire_contribution": round(a_score, 1),
                "gaze_poise_contribution": round(e_score, 1),
                "facial_composure_contribution": round(composure_score, 1)
            }
        }
