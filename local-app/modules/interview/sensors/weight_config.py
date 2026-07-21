import logging
from typing import Dict, Optional
from copy import deepcopy

logger = logging.getLogger(__name__)

# Default weights for each sensor category
DEFAULT_WEIGHTS: Dict[str, float] = {
    "posture": 0.15,
    "eye_contact": 0.15,
    "body_language": 0.15,
    "attire": 0.10,
    "confidence": 0.10,
    "facial_expression": 0.10,
    "voice": 0.15,
    "engagement": 0.05,
    "professional_presence": 0.05,
}


class WeightConfig:
    """
    Manages adjustable weights for all sensors.
    Weights can be changed at runtime — even mid-session — by a trainer.
    They auto-normalize so the total always sums to 1.0.
    """

    def __init__(self, initial_weights: Optional[Dict[str, float]] = None):
        self._weights = deepcopy(initial_weights or DEFAULT_WEIGHTS)
        self._normalize()

    def _normalize(self):
        """Normalize weights so they sum to 1.0."""
        total = sum(self._weights.values())
        if total > 0:
            self._weights = {k: v / total for k, v in self._weights.items()}
        else:
            # If all zeroed out, reset to equal distribution
            n = len(self._weights)
            self._weights = {k: 1.0 / n for k in self._weights}

    @property
    def weights(self) -> Dict[str, float]:
        return deepcopy(self._weights)

    def update_weight(self, sensor_name: str, value: float):
        """Update a single sensor weight (0.0 to 1.0 raw scale). Auto-normalizes."""
        if sensor_name not in self._weights:
            raise ValueError(f"Unknown sensor: {sensor_name}. Available: {list(self._weights.keys())}")
        value = max(0.0, min(1.0, value))
        self._weights[sensor_name] = value
        self._normalize()
        logger.info(f"Weight updated: {sensor_name}={value:.2f} -> normalized: {self._weights}")

    def update_weights(self, updates: Dict[str, float]):
        """Bulk update multiple weights at once."""
        for name, value in updates.items():
            if name in self._weights:
                self._weights[name] = max(0.0, min(1.0, value))
        self._normalize()
        logger.info(f"Weights bulk updated -> {self._weights}")

    def get_weight(self, sensor_name: str) -> float:
        return self._weights.get(sensor_name, 0.0)

    def compute_weighted_score(self, scores: Dict[str, float]) -> float:
        """
        Given raw sensor scores (each 0-100), compute the final weighted score.
        Uses ratio-based weighted average: score = Σ(score × weight) / Σ(active_weights).
        Sensors with weight 0 are excluded entirely from the calculation.
        """
        numerator = 0.0
        denominator = 0.0
        for sensor, weight in self._weights.items():
            if weight <= 0:
                continue
            raw = scores.get(sensor, 0.0)
            numerator += raw * weight
            denominator += weight
        if denominator <= 0:
            return 0.0
        return round(numerator / denominator, 2)

    def to_dict(self) -> Dict[str, float]:
        return deepcopy(self._weights)


# Global default instance (can be overridden per session)
global_weights = WeightConfig()
