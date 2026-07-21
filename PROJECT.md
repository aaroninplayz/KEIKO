# Project: Keiko Real-Time Interview Analyzer

## Architecture
The Keiko Real-Time Interview Analyzer is a FastAPI + WebSocket application that performs real-time visual, vocal, and textual evaluation of a candidate during an interview session.
- **WebSocket Gateway**: Exposes `/api/v1/interview/ws/{session_id}` where clients stream base64 video frames and audio chunks. Telemetry updates (`metrics_update`) are returned in real-time.
- **Visual Sensor Array**:
  - Posture Analyzer (`posture_analyzer.py` via MediaPipe)
  - Eye Contact Analyzer (`eye_contact_analyzer.py` via MediaPipe)
  - Body Language Analyzer (`body_language_analyzer.py` via MediaPipe)
  - Attire Analyzer (`attire_analyzer.py` via OpenCV)
  - Facial Expression & Emotion Sensor (`facial_expression_analyzer.py` via MediaPipe FaceLandmarker blendshapes)
  - Composite Engagement Tracking (Combines gaze, head movement, expressiveness, response latency)
- **Vocal & Speech Sensor Array**:
  - Voice Analyzer (`voice_analyzer.py` performing audio buffering and Whisper STT / API fallback)
  - Voice modulation, speaking pace, speech clarity, and fluency / hesitation scores (0-100)
- **Evaluation & Report Engine**:
  - Central Evaluator (`central_evaluator.py`) evaluates candidate transcript and metadata, scoring overall, technical, communication, behavioral, and presence dimensions.
  - Report Generator (`report_generator.py`) produces the final recruiter report with all score breakdowns.

## Code Layout
- `core/config.py`: Configuration parameters, including STT and LLM configurations.
- `modules/interview/router.py`: REST endpoints and WebSocket handler for audio/video stream.
- `modules/interview/orchestrator.py`: Multi-threaded frame and audio processing orchestrator.
- `modules/interview/sensors/`:
  - `posture_analyzer.py`, `eye_contact_analyzer.py`, `body_language_analyzer.py`, `attire_analyzer.py` (Existing)
  - `facial_expression_analyzer.py` (New facial expression sensor)
  - `voice_analyzer.py` (Replaces stub with real audio features & STT)
  - `confidence_metric.py`, `weight_config.py` (Weighted scoring configuration)
- `modules/interview/agents/`:
  - `central_evaluator.py` (Scoring and dialogue evaluation)
  - `report_generator.py` (Recruiter report builder)
  - `question_generator.py` (Dialectical state prompt driver)

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | E2E Testing Track | Design E2E test infra and test cases (Tiers 1-4) in `scratch/test_pipeline.py` or new suite | None | DONE |
| 2 | Live Audio Capture & Speech-to-Text | Extend config, implement audio WebSocket chunk buffering, local Whisper / API fallback | None | DONE |
| 3 | Voice & Speech Analysis Sensors | Replace stub `voice_analyzer.py` with modulation, pace, clarity, fluency scores (0-100) | M2 | DONE |
| 4 | Facial Expressions & Engagement | Implement facial expression sensor (MediaPipe blendshapes) and composite engagement metrics | None | DONE |
| 5 | Recruiter Report & High-Level Evaluation | Score Professional Presence, Technical, Communication, Behavioral; update report generator | M3, M4 | DONE |
| 6 | Robustness, Audits & Final Hardening | Handle missing models, WebSocket exception safety, pass 100% tests & Forensic Audit | M1, M5 | DONE |
| 7 | Audio-Visual Composure & Stress/Resilience Tracking | Calculate composure & stress/resilience in orchestrator telemetry | M3, M4 | IN_PROGRESS |
| 8 | Learning & Cultural Fit Heuristics | Implement learning potential & cultural fit in evaluator | None | PLANNED |
| 9 | Unified Role Alignment & Reporting | Combine match score with overall score in recruiter report | M8 | PLANNED |
| 10 | Final Audit Resolution | Pass all unit test assertions & clean Forensic Audit | M7, M9 | PLANNED |

## Interface Contracts
### Client ↔ WebSocket `/api/v1/interview/ws/{session_id}`
- **Client to Server**:
  - `{"type": "video_frame", "data": "<base64_jpeg>"}`
  - `{"type": "audio_chunk", "data": "<base64_wav_or_webm>"}`
  - `{"type": "update_weights", "weights": {"posture": 0.15, "eye_contact": 0.15, "attire": 0.1, "body_language": 0.15, "confidence": 0.15, "voice": 0.15, "facial_expression": 0.15}}`
  - `{"type": "submit_answer", "question": "string", "answer": "string"}`
- **Server to Client**:
  - `{"type": "connected", "session_id": "string", "weights": {...}}`
  - `{"type": "metrics_update", "timestamp": float, "weighted_overall": float, "weights": {...}, "sensors": {...}}`
  - `{"type": "new_question", "question": "string", "index": int}`
  - `{"type": "interview_complete", "report": {...}}`
