import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class EngagementTracker:
    """
    Composite meta-sensor that tracks candidate engagement.
    Combines visual gaze consistency, physical head engagement/nodding,
    facial expressiveness (emotional responsiveness), and response latency.
    """

    def calculate(
        self,
        eye_contact: Dict[str, Any],
        body_language: Dict[str, Any],
        facial_expression: Dict[str, Any],
        latency: Optional[float] = None
    ) -> Dict[str, Any]:
        
        # 1. Gaze Consistency
        eye_details = eye_contact.get("details", {})
        if eye_details.get("detected") and eye_details.get("iris_available"):
            deviation = eye_details.get("deviation", 0.0)
            # Map deviation (0.0 to 0.5+) to score (100 to 0)
            gaze_score = max(0.0, min(100.0, 100.0 - deviation * 200.0))
        else:
            gaze_score = eye_contact.get("score", 70.0)

        # 2. Head Nodding/Movement
        body_details = body_language.get("details", {})
        if body_details.get("detected"):
            head_score = body_details.get("head_engagement", 70.0)
        else:
            head_score = body_language.get("score", 70.0)

        # 3. Facial Expressiveness
        face_details = facial_expression.get("details", {})
        if face_details.get("detected") and not face_details.get("mock"):
            neutral_prob = face_details.get("scores", {}).get("neutral", 0.7)
            # High neutral score means static face (less expressive).
            # Perfect expression score is when they show moderate expressions.
            expressiveness_score = max(30.0, min(100.0, 100.0 - abs(neutral_prob - 0.4) * 80.0))
        else:
            expressiveness_score = facial_expression.get("score", 70.0)

        # Base average
        base_score = (gaze_score * 0.40) + (head_score * 0.30) + (expressiveness_score * 0.30)

        modifiers = []
        modified_score = base_score

        # 4. Response Latency Modifiers
        if latency is not None:
            if latency > 15.0:
                # Penalize delay in answering
                penalty = min(30.0, (latency - 15.0) * 1.5)
                modified_score -= penalty
                modifiers.append({"type": "Response Latency Penalty", "effect": -round(penalty, 1)})
            elif latency < 4.0:
                # Reward swift reply
                modified_score += 5.0
                modifiers.append({"type": "Swift Response Bonus", "effect": 5.0})

        final_score = max(0.0, min(100.0, modified_score))

        return {
            "sensor_type": "engagement",
            "score": round(final_score, 1),
            "details": {
                "base_score": round(base_score, 1),
                "gaze_consistency": round(gaze_score, 1),
                "head_nodding": round(head_score, 1),
                "facial_expressiveness": round(expressiveness_score, 1),
                "response_latency": round(latency, 2) if latency is not None else None,
                "modifiers": modifiers,
            }
        }
