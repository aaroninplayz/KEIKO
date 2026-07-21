import os
import json
import yaml

class HRAggregator:
    def __init__(self, config_path="config.yaml", telemetry_path="telemetry.json"):
        self.config_path = config_path
        self.telemetry_path = telemetry_path
        
        # Hardcoded class scores for simple qualitative-to-quantitative mapping
        self.grade_mappings = {
            "posture": {"good": 1.0, "slouched": 0.3, "untrained": 0.5, "disabled": 0.0, "Not Trained": 0.5},
            "eye_contact": {"focused": 1.0, "distracted": 0.2, "untrained": 0.5, "disabled": 0.0, "Not Trained": 0.5},
            "attire": {"formal": 1.0, "casual": 0.4, "untrained": 0.5, "disabled": 0.0, "Not Trained": 0.5},
            "confidence": {"confident": 1.0, "nervous": 0.3, "untrained": 0.5, "disabled": 0.0, "Not Trained": 0.5},
            "emotions": {"confident": 1.0, "neutral": 0.8, "stressed": 0.3, "untrained": 0.5, "disabled": 0.0, "Not Trained": 0.5}
        }

    def load_config(self):
        with open(self.config_path, "r") as f:
            return yaml.safe_load(f)

    def calculate_grade(self, detector_metrics):
        """
        Takes real-time raw predictions from AsyncDetectorManager, combines them 
        based on active weights/states, and outputs a final percentage score.
        """
        try:
            config = self.load_config()
        except Exception:
            # Fallback if config is temporarily locked
            return 0.0, "N/A", {}

        total_active_weight = 0.0
        weighted_score_sum = 0.0
        breakdown = {}

        # Loop through each detector defined in config
        for key, cfg in config["detectors"].items():
            metrics = detector_metrics.get(key, {})
            enabled = cfg["enabled"]
            weight = cfg["weight"]
            
            # Read prediction label
            label = metrics.get("label", "Not Trained")
            trained = metrics.get("trained", False)
            
            # Map qualitative label to float grade (0.0 to 1.0)
            detector_grade_map = self.grade_mappings.get(key, {})
            raw_grade = detector_grade_map.get(label, 0.5) # default to neutral 50%
            
            # Track separate breakdown scores for UI
            breakdown[key] = {
                "label": label,
                "score_percent": int(raw_grade * 100),
                "enabled": enabled,
                "weight": weight,
                "trained": trained
            }
            
            if enabled and trained:
                total_active_weight += weight
                weighted_score_sum += raw_grade * weight

        # If everything is disabled or untrained, default to 100% baseline to avoid DivisionByZero
        if total_active_weight == 0.0:
            final_score = 1.0
        else:
            # Normalize active weights so disabled/untrained models don't penalize the user
            final_score = weighted_score_sum / total_active_weight

        final_percent = int(final_score * 100)

        # Assign descriptive qualitative rank
        if final_percent >= 85:
            ranking = "EXCELLENT"
        elif final_percent >= 70:
            ranking = "GOOD PASS"
        elif final_percent >= 50:
            ranking = "MARGINAL PASS"
        else:
            ranking = "NEEDS IMPROVEMENT"

        # Prepare payload to export
        telemetry_payload = {
            "final_score_percent": final_percent,
            "overall_rating": ranking,
            "individual_breakdown": breakdown
        }

        # Write to telemetry.json file
        self.export_telemetry(telemetry_payload)

        return final_percent, ranking, breakdown

    def export_telemetry(self, payload):
        """Thread-safe and fast JSON writing."""
        temp_path = self.telemetry_path + ".tmp"
        try:
            with open(temp_path, "w") as f:
                json.dump(payload, f, indent=2)
            # Atomic replace to prevent readers from reading a half-written file
            os.replace(temp_path, self.telemetry_path)
        except Exception:
            pass # Suppress temporary IO errors
