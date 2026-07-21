# Keiko Real-Time Interview Analyzer — API & WebSocket Specification

This document provides the complete, high-fidelity integration specification for the Keiko Real-Time CV & AI Interview Module. Developers can construct any frontend interface (web, desktop, or mobile) and integrate it seamlessly with this backend by adhering to this spec.

---

## 📡 1. WebSocket Endpoint

All real-time webcam frame streaming, sensor scoring, and dynamic weight changes occur over a single bi-directional WebSocket connection.

* **Base URL**: `ws://localhost:8000/api/v1/interview/ws/{session_id}`
* **Session ID (`{session_id}`)**: Any unique alphanumeric string identifying the current interview session (e.g., `sess_a3c10`). This allows multi-user scoping and session-specific dynamic weight configurations.

### A. Connection Handshake
Upon successful connection, the server immediately sends a `connected` JSON event to synchronize weights:

```json
{
  "type": "connected",
  "session_id": "sess_a3c10",
  "weights": {
    "posture": 0.15,
    "eye_contact": 0.15,
    "body_language": 0.15,
    "attire": 0.10,
    "confidence": 0.10,
    "facial_expression": 0.10,
    "voice": 0.15,
    "engagement": 0.05,
    "professional_presence": 0.05
  }
}
```

---

## 📡 2. Client-to-Server Messages (Input)

### A. Video Frame Payload (`video_frame`)
Send JPEG/PNG frames captured from the client webcam at a recommended frequency of **5 to 10 FPS**. The frames should be encoded as a Base64 string.

```json
{
  "type": "video_frame",
  "data": "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAMCAgMCAgMDAwMEAwMEBQgFBQQEBQoHBwYIDAoMDAsKCwsNDhIQDQ4RDgsLEBYQERMUFRUVDA8XGBYUGBIUFRT..."
}
```
> [!NOTE]
> The backend gracefully handles both raw base64 data and standard data URI prefixes (e.g. `data:image/jpeg;base64,...`).

### B. Live Audio Chunk Payload (`audio_chunk`)
Send raw 16kHz mono 16-bit PCM audio chunks captured from the candidate microphone:

```json
{
  "type": "audio_chunk",
  "data": "a1b2c3d4e5f6g7h8..."
}
```
> [!NOTE]
> The backend receives these chunks, appends them to a session-specific buffer, and transcribes them when the candidate submits their response.

### C. Dynamically Update Weights (`update_weights`)
To change the weight coefficients for calculating the candidate's final score at runtime:

```json
{
  "type": "update_weights",
  "weights": {
    "posture": 0.15,
    "eye_contact": 0.15,
    "body_language": 0.15,
    "attire": 0.10,
    "confidence": 0.10,
    "facial_expression": 0.10,
    "voice": 0.15,
    "engagement": 0.05,
    "professional_presence": 0.05
  }
}
```
> [!IMPORTANT]
> The backend automatically normalizes these weight values. For example, if you send all `1.0`, they will auto-scale to equal divisions (`0.20` each) so the sum is always exactly `1.0`.

---

## 📥 3. Server-to-Client Messages (Telemetry & Scores)

The backend processes incoming frames asynchronously. To optimize CPU usage, it throttles calculations to every 3rd frame (~3 FPS output for 10 FPS input) and broadcasts telemetry packets.

### A. Telemetry Metrics Update (`metrics_update`)
Broadcasted by the server when a frame finishes processing:

```json
{
  "type": "metrics_update",
  "timestamp": 1780167412.164,
  "weighted_overall": 75.82,
  "weights": {
    "posture": 0.15,
    "eye_contact": 0.15,
    "body_language": 0.15,
    "attire": 0.10,
    "confidence": 0.10,
    "facial_expression": 0.10,
    "voice": 0.15,
    "engagement": 0.05,
    "professional_presence": 0.05
  },
  "sensors": {
    "posture": {
      "sensor_type": "posture",
      "score": 82.5,
      "details": {
        "detected": true,
        "shoulder_alignment": 94.2,
        "spine_angle": 158.1,
        "spine_score": 75.6,
        "head_alignment": 80.0,
        "is_slouching": false
      }
    },
    "eye_contact": {
      "sensor_type": "eye_contact",
      "score": 92.1,
      "details": {
        "detected": true,
        "iris_available": true,
        "horizontal_ratio": 0.505,
        "deviation": 0.005,
        "is_making_contact": true,
        "raw_score": 98.3
      }
    },
    "body_language": {
      "sensor_type": "body_language",
      "score": 68.4,
      "details": {
        "detected": true,
        "openness": 78.4,
        "gesture_activity": 50.0,
        "head_engagement": 55.0,
        "hand_activity_raw": 0.012
      }
    },
    "attire": {
      "sensor_type": "attire",
      "score": 85.0,
      "details": {
        "detected": true,
        "saturation_uniformity": 88.0,
        "brightness_consistency": 82.0,
        "color_simplicity": 85.0,
        "dominant_colors": 2
      }
    },
    "confidence": {
      "sensor_type": "confidence",
      "score": 81.0,
      "details": {
        "sub_weights": {
          "posture": 0.3,
          "eye_contact": 0.4,
          "body_language": 0.3
        },
        "input_scores": {
          "posture": 82.5,
          "eye_contact": 92.1,
          "body_language": 68.4
        }
      }
    },
    "facial_expression": {
      "sensor_type": "facial_expression",
      "score": 88.2,
      "details": {
        "detected": true,
        "primary": "neutral",
        "scores": {
          "neutral": 0.8,
          "happy": 0.1,
          "confused": 0.05,
          "nervous": 0.05
        },
        "mock": false
      }
    },
    "voice": {
      "sensor_type": "voice",
      "score": 82.5,
      "details": {
        "pace": 85.0,
        "modulation": 80.0,
        "clarity": 85.0,
        "fluency": 80.0,
        "wpm": 138.5,
        "filler_count": 2
      }
    },
    "engagement": {
      "sensor_type": "engagement",
      "score": 84.5,
      "details": {
        "base_score": 84.5,
        "gaze_consistency": 95.0,
        "head_nodding": 70.0,
        "facial_expressiveness": 80.0,
        "response_latency": 4.5,
        "modifiers": []
      }
    },
    "professional_presence": {
      "sensor_type": "professional_presence",
      "score": 83.2,
      "details": {
        "posture_contribution": 82.5,
        "attire_contribution": 85.0,
        "gaze_poise_contribution": 92.1,
        "facial_composure_contribution": 95.0
      }
    }
  }
}
```

### B. Fallback Metrics Update (No Person Detected)
If a frame does not contain a visible face or body:

```json
{
  "type": "metrics_update",
  "timestamp": 1780167412.164,
  "weighted_overall": 0.0,
  "weights": { ... },
  "sensors": {
    "posture": { "sensor_type": "posture", "score": 0.0, "details": { "detected": false } },
    "eye_contact": { "sensor_type": "eye_contact", "score": 0.0, "details": { "detected": false } },
    "body_language": { "sensor_type": "body_language", "score": 0.0, "details": { "detected": false } },
    "attire": { "sensor_type": "attire", "score": 0.0, "details": { "detected": false } },
    "confidence": { "sensor_type": "confidence", "score": 0.0, "details": { ... } },
    "facial_expression": { "sensor_type": "facial_expression", "score": 0.0, "details": { "detected": false } },
    "voice": { "sensor_type": "voice", "score": 0.0, "details": { "wpm": 0 } },
    "engagement": { "sensor_type": "engagement", "score": 0.0, "details": { "base_score": 0.0 } },
    "professional_presence": { "sensor_type": "professional_presence", "score": 0.0, "details": { ... } }
  }
}
```


### C. Weights Synchronized Confirmation (`weights_updated`)
Sent by the server immediately after updating a session's weights:

```json
{
  "type": "weights_updated",
  "weights": {
    "posture": 0.15,
    "eye_contact": 0.15,
    "body_language": 0.15,
    "attire": 0.10,
    "confidence": 0.10,
    "facial_expression": 0.10,
    "voice": 0.15,
    "engagement": 0.05,
    "professional_presence": 0.05
  }
}
```

---

## 🌐 4. HTTP API Endpoints (Weight CRUD)

For static configurations or standard HTTP integrations, weight updates can also be query-read and written via normal endpoints:

### A. Get Weights for a Session
* **Method & Path**: `GET /api/v1/interview/config/weights/{session_id}`
* **Response Payload (`200 OK`)**:
  ```json
  {
    "session_id": "sess_a3c10",
    "weights": {
      "posture": 0.15,
      "eye_contact": 0.15,
      "body_language": 0.15,
      "attire": 0.10,
      "confidence": 0.10,
      "facial_expression": 0.10,
      "voice": 0.15,
      "engagement": 0.05,
      "professional_presence": 0.05
    }
  }
  ```

### B. Update Weights for a Session
* **Method & Path**: `PUT /api/v1/interview/config/weights/{session_id}`
* **Request Content-Type**: `application/json`
* **Request Payload**:
  ```json
  {
    "posture": 0.15,
    "eye_contact": 0.15,
    "body_language": 0.15,
    "attire": 0.10,
    "confidence": 0.10,
    "facial_expression": 0.10,
    "voice": 0.15,
    "engagement": 0.05,
    "professional_presence": 0.05
  }
  ```
* **Response Payload (`200 OK`)**:
  ```json
  {
    "session_id": "sess_a3c10",
    "weights": {
      "posture": 0.15,
      "eye_contact": 0.15,
      "body_language": 0.15,
      "attire": 0.10,
      "confidence": 0.10,
      "facial_expression": 0.10,
      "voice": 0.15,
      "engagement": 0.05,
      "professional_presence": 0.05
    }
  }
  ```

### C. Get Global Default Weights
* **Method & Path**: `GET /api/v1/interview/config/weights`
* **Response Payload (`200 OK`)**:
  ```json
  {
    "weights": {
      "posture": 0.15,
      "eye_contact": 0.15,
      "body_language": 0.15,
      "attire": 0.10,
      "confidence": 0.10,
      "facial_expression": 0.10,
      "voice": 0.15,
      "engagement": 0.05,
      "professional_presence": 0.05
    }
  }
  ```

