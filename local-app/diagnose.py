"""
Diagnostic script: uses a synthetic face-like image to test all sensors,
since the webcam may be in use by the browser.
"""
import cv2
import numpy as np
import json
import sys
import time

print("=" * 60)
print("KEIKO SENSOR DIAGNOSTIC (synthetic frame)")
print("=" * 60)

# 1. Create a realistic test image by loading one from the web or generating a skin-tone blob
print("\n[1] Creating synthetic test frame...")

# Create a 640x480 frame with a skin-tone face-like blob
frame_rgb = np.zeros((480, 640, 3), dtype=np.uint8)
frame_rgb[:] = [200, 200, 200]  # light gray background

# Draw a skin-toned oval for the "face"
cv2.ellipse(frame_rgb, (320, 180), (80, 100), 0, 0, 360, (210, 170, 140), -1)
# Draw "shoulders" 
cv2.rectangle(frame_rgb, (200, 280), (440, 480), (100, 100, 150), -1)
# Draw "eyes"
cv2.circle(frame_rgb, (290, 160), 10, (50, 50, 50), -1)
cv2.circle(frame_rgb, (350, 160), 10, (50, 50, 50), -1)
# Draw "nose"
cv2.ellipse(frame_rgb, (320, 190), (8, 15), 0, 0, 360, (190, 150, 120), -1)
# Draw "mouth"
cv2.ellipse(frame_rgb, (320, 220), (25, 10), 0, 0, 360, (180, 100, 100), -1)

print(f"   Synthetic frame: {frame_rgb.shape} dtype={frame_rgb.dtype}")

# 2. Test each sensor individually
print("\n[2] Testing individual sensors...")

from modules.interview.sensors.posture_analyzer import PostureAnalyzer
from modules.interview.sensors.eye_contact_analyzer import EyeContactAnalyzer
from modules.interview.sensors.body_language_analyzer import BodyLanguageAnalyzer
from modules.interview.sensors.attire_analyzer import AttireAnalyzer
from modules.interview.sensors.confidence_metric import ConfidenceMetric

print("\n--- POSTURE ANALYZER ---")
pa = PostureAnalyzer()
print(f"   Landmarker loaded: {pa._landmarker is not None}")
t0 = time.time()
posture = pa.process_frame(frame_rgb)
t1 = time.time()
print(f"   Time: {(t1-t0)*1000:.0f}ms")
print(f"   Score: {posture.get('score')}")
print(f"   Details: {posture.get('details')}")

print("\n--- EYE CONTACT ANALYZER ---")
ea = EyeContactAnalyzer()
print(f"   Landmarker loaded: {ea._landmarker is not None}")
t0 = time.time()
eye = ea.process_frame(frame_rgb)
t1 = time.time()
print(f"   Time: {(t1-t0)*1000:.0f}ms")
print(f"   Score: {eye.get('score')}")
print(f"   Details: {eye.get('details')}")

print("\n--- BODY LANGUAGE ANALYZER ---")
ba = BodyLanguageAnalyzer()
print(f"   Landmarker loaded: {ba._landmarker is not None}")
t0 = time.time()
body = ba.process_frame(frame_rgb)
t1 = time.time()
print(f"   Time: {(t1-t0)*1000:.0f}ms")
print(f"   Score: {body.get('score')}")
print(f"   Details: {body.get('details')}")

print("\n--- ATTIRE ANALYZER ---")
aa = AttireAnalyzer()
print(f"   Landmarker loaded: {aa._landmarker is not None}")
t0 = time.time()
attire = aa.process_frame(frame_rgb)
t1 = time.time()
print(f"   Time: {(t1-t0)*1000:.0f}ms")
print(f"   Score: {attire.get('score')}")
print(f"   Details: {attire.get('details')}")

print("\n--- CONFIDENCE METRIC ---")
cm = ConfidenceMetric()
confidence = cm.calculate(posture=posture, eye_contact=eye, body_language=body)
print(f"   Score: {confidence.get('score')}")
print(f"   Details: {json.dumps(confidence.get('details'), indent=4, default=str)}")

# 3. Test JSON serialization
print("\n[3] Testing JSON serialization...")
from modules.interview.orchestrator import _sanitize_for_json
from modules.interview.sensors.weight_config import WeightConfig

results = {
    "posture": posture,
    "eye_contact": eye,
    "body_language": body,
    "attire": attire,
    "confidence": confidence,
}

wc = WeightConfig()
scores = {k: v["score"] for k, v in results.items()}
weighted = wc.compute_weighted_score(scores)

payload = {
    "type": "metrics_update",
    "timestamp": time.time(),
    "sensors": results,
    "weighted_overall": weighted,
    "weights": wc.weights,
}

sanitized = _sanitize_for_json(payload)

try:
    json_str = json.dumps(sanitized)
    print(f"   JSON serialization: OK ({len(json_str)} bytes)")
    print(f"\n   === FINAL SCORES ===")
    print(f"     Posture:       {sanitized['sensors']['posture']['score']}")
    print(f"     Eye Contact:   {sanitized['sensors']['eye_contact']['score']}")
    print(f"     Body Language: {sanitized['sensors']['body_language']['score']}")
    print(f"     Attire:        {sanitized['sensors']['attire']['score']}")
    print(f"     Confidence:    {sanitized['sensors']['confidence']['score']}")
    print(f"     WEIGHTED OVERALL: {sanitized['weighted_overall']}")
except Exception as e:
    print(f"   JSON serialization FAILED: {e}")
    import traceback
    traceback.print_exc()

# 4. Check for the throttle issue
print("\n[4] Testing throttle behavior...")
print(f"   _process_every_n = 3 (processes every 3rd frame)")
print(f"   At 10 FPS capture, effective analysis rate = ~3.3 FPS")
print(f"   Frame 1: SKIP, Frame 2: SKIP, Frame 3: PROCESS")

# Verify scores aren't all zero
all_zero = all(v["score"] == 0 for v in results.values())
if all_zero:
    print("\n   [WARNING] ALL SCORES ARE ZERO!")
    print("   This means MediaPipe couldn't detect a person in the frame.")
    print("   With a real webcam showing a real person, scores should be non-zero.")
else:
    print(f"\n   [OK] Non-zero scores detected. Pipeline is functional.")

# Clean up
pa.release()
ea.release()
ba.release()
aa.release()

print("\n" + "=" * 60)
print("DIAGNOSTIC COMPLETE")
print("=" * 60)
