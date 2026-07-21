import os
import sys
import time
import yaml
import cv2
import threading
from flask import Flask, Response, jsonify, request

# Import our modular pipeline
from detectors import AsyncDetectorManager
from aggregator import HRAggregator

# Initialize Flask
app = Flask(__name__)

# Global instances
detector_manager = None
aggregator = None
latest_frame = None
frame_lock = threading.Lock()

# Load initial config
def load_config():
    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)

def save_config(config_data):
    with open("config.yaml", "w") as f:
        yaml.safe_dump(config_data, f, default_flow_style=False)

# Background video reader thread (keeps camera warm and grabs frames)
def video_capture_loop():
    global latest_frame
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("ERROR: Could not open webcam.")
        return

    # Warm up camera
    time.sleep(1.0)
    
    while detector_manager.running:
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.01)
            continue
            
        # Update background queue for models to process
        detector_manager.update_frame(frame)
        
        # Draw some high-tech scanning overlays on the raw frame for the live stream
        annotated_frame = frame.copy()
        h, w, _ = annotated_frame.shape
        
        # Futuristic scanlines & HUD
        cv2.rectangle(annotated_frame, (int(w*0.1), int(h*0.1)), (int(w*0.9), int(h*0.9)), (138, 43, 226), 1) # Purple scan frame
        cv2.line(annotated_frame, (int(w*0.1), int(h*0.5)), (int(w*0.9), int(h*0.5)), (138, 43, 226), 1) # Reticle line
        
        # Corners of the tracking frame
        cw, ch = int(w*0.1), int(h*0.1)
        cl = 30 # corner length
        cv2.line(annotated_frame, (cw, ch), (cw+cl, ch), (138, 43, 226), 3)
        cv2.line(annotated_frame, (cw, ch), (cw, ch+cl), (138, 43, 226), 3)
        
        cw, ch = int(w*0.9), int(h*0.1)
        cv2.line(annotated_frame, (cw, ch), (cw-cl, ch), (138, 43, 226), 3)
        cv2.line(annotated_frame, (cw, ch), (cw, ch+cl), (138, 43, 226), 3)
        
        cw, ch = int(w*0.1), int(h*0.9)
        cv2.line(annotated_frame, (cw, ch), (cw+cl, ch), (138, 43, 226), 3)
        cv2.line(annotated_frame, (cw, ch), (cw, ch-cl), (138, 43, 226), 3)
        
        cw, ch = int(w*0.9), int(h*0.9)
        cv2.line(annotated_frame, (cw, ch), (cw-cl, ch), (138, 43, 226), 3)
        cv2.line(annotated_frame, (cw, ch), (cw, ch-cl), (138, 43, 226), 3)

        # Print scanning indicator
        cv2.putText(annotated_frame, "VISION SCANNER ACTIVE", (20, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

        with frame_lock:
            latest_frame = annotated_frame.copy()
            
        time.sleep(0.03) # Cap video capture loop at ~30 FPS

    cap.release()

# MJPEG Generator
def generate_mjpeg_stream():
    global latest_frame
    while detector_manager.running:
        with frame_lock:
            if latest_frame is None:
                img = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(img, "Webcam Connecting...", (120, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
                _, jpeg = cv2.imencode('.jpg', img)
            else:
                _, jpeg = cv2.imencode('.jpg', latest_frame)
                
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n\r\n')
        time.sleep(0.04) # Output stream capped at ~25 FPS

# Web endpoints
@app.route('/')
def index():
    return Response(HTML_DASHBOARD, mimetype='text/html')

@app.route('/video_feed')
def video_feed():
    return Response(generate_mjpeg_stream(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/metrics')
def get_metrics():
    # Read raw model outputs
    raw_results = detector_manager.get_latest_results()
    # Apply weights and compile structured telemetry
    final_score, rating, breakdown = aggregator.calculate_grade(raw_results)
    
    return jsonify({
        "final_score": final_score,
        "rating": rating,
        "breakdown": breakdown
    })

@app.route('/config', methods=['POST'])
def update_config():
    data = request.json
    try:
        current_config = load_config()
        
        # Parse payload and update properties dynamically
        key = data.get("detector_key")
        if key in current_config["detectors"]:
            if "enabled" in data:
                current_config["detectors"][key]["enabled"] = bool(data["enabled"])
            if "weight" in data:
                current_config["detectors"][key]["weight"] = float(data["weight"])
            if "temperature" in data:
                current_config["detectors"][key]["temperature"] = float(data["temperature"])
            if "threshold" in data:
                current_config["detectors"][key]["threshold"] = float(data["threshold"])
                
            save_config(current_config)
            return jsonify({"status": "success", "message": f"Updated detector: {key}"})
        else:
            return jsonify({"status": "error", "message": "Invalid detector key"}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

HTML_DASHBOARD = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>HR Interview Vision AI</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #0c0d12;
            --card-bg: rgba(22, 24, 35, 0.6);
            --border-color: rgba(255, 255, 255, 0.08);
            --text-primary: #f3f4f6;
            --text-secondary: #9ca3af;
            --accent-color: #8b5cf6;
            --accent-hover: #a78bfa;
            --success-color: #10b981;
            --warning-color: #f59e0b;
            --danger-color: #ef4444;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Plus Jakarta Sans', sans-serif;
            background-color: var(--bg-color);
            color: var(--text-primary);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            overflow-x: hidden;
        }

        header {
            padding: 24px 40px;
            background: linear-gradient(180deg, rgba(12, 13, 18, 0.8) 0%, rgba(12, 13, 18, 0) 100%);
            border-bottom: 1px solid var(--border-color);
            backdrop-filter: blur(12px);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .logo-section h1 {
            font-size: 1.5rem;
            font-weight: 700;
            letter-spacing: -0.5px;
            background: linear-gradient(90deg, #a78bfa 0%, #8b5cf6 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .logo-section p {
            font-size: 0.8rem;
            color: var(--text-secondary);
            margin-top: 4px;
        }

        .status-badge {
            background: rgba(16, 185, 129, 0.1);
            border: 1px solid rgba(16, 185, 129, 0.2);
            color: var(--success-color);
            padding: 6px 14px;
            border-radius: 99px;
            font-size: 0.8rem;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .pulse-dot {
            width: 8px;
            height: 8px;
            background-color: var(--success-color);
            border-radius: 50%;
            animation: pulse 1.5s infinite;
        }

        @keyframes pulse {
            0% { transform: scale(0.9); opacity: 0.6; }
            50% { transform: scale(1.2); opacity: 1; }
            100% { transform: scale(0.9); opacity: 0.6; }
        }

        main {
            flex: 1;
            padding: 40px;
            display: grid;
            grid-template-columns: 1.2fr 1fr;
            gap: 40px;
            max-width: 1600px;
            margin: 0 auto;
            width: 100%;
        }

        .card {
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            backdrop-filter: blur(20px);
            border-radius: 24px;
            padding: 30px;
            display: flex;
            flex-direction: column;
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3);
        }

        .video-container {
            position: relative;
            width: 100%;
            border-radius: 16px;
            overflow: hidden;
            border: 1px solid var(--border-color);
            background: #000;
            aspect-ratio: 4/3;
        }

        .video-feed {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }

        .overall-score-panel {
            display: flex;
            align-items: center;
            justify-content: space-around;
            margin-top: 30px;
            padding: 24px;
            background: rgba(255, 255, 255, 0.02);
            border-radius: 20px;
            border: 1px solid var(--border-color);
        }

        .score-circle {
            position: relative;
            width: 120px;
            height: 120px;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .score-circle svg {
            width: 100%;
            height: 100%;
            transform: rotate(-90deg);
        }

        .score-circle circle {
            fill: none;
            stroke-width: 8;
        }

        .score-circle .bg-circle {
            stroke: rgba(255, 255, 255, 0.05);
        }

        .score-circle .val-circle {
            stroke: var(--accent-color);
            stroke-linecap: round;
            transition: stroke-dashoffset 0.6s ease;
        }

        .score-text {
            position: absolute;
            font-size: 1.8rem;
            font-weight: 700;
        }

        .rating-label h2 {
            font-size: 1.3rem;
            font-weight: 700;
            color: var(--text-primary);
        }

        .rating-label p {
            font-size: 0.9rem;
            color: var(--text-secondary);
            margin-top: 4px;
        }

        .controls-panel h3 {
            font-size: 1.2rem;
            font-weight: 600;
            margin-bottom: 24px;
            letter-spacing: -0.3px;
        }

        .detector-row {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 20px;
            margin-bottom: 16px;
            transition: all 0.3s ease;
        }

        .detector-row:hover {
            border-color: rgba(139, 92, 246, 0.3);
            background: rgba(255, 255, 255, 0.03);
        }

        .detector-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 14px;
        }

        .detector-title {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .detector-title h4 {
            font-size: 1rem;
            font-weight: 600;
        }

        .metric-badge {
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 0.75rem;
            font-weight: 700;
        }

        .badge-trained { background: rgba(16, 185, 129, 0.1); color: var(--success-color); }
        .badge-untrained { background: rgba(239, 68, 68, 0.1); color: var(--danger-color); }
        .badge-disabled { background: rgba(255, 255, 255, 0.05); color: var(--text-secondary); }

        .slider-group {
            margin-bottom: 10px;
        }

        .slider-label {
            display: flex;
            justify-content: space-between;
            font-size: 0.8rem;
            color: var(--text-secondary);
            margin-bottom: 6px;
        }

        input[type="range"] {
            width: 100%;
            -webkit-appearance: none;
            background: rgba(255, 255, 255, 0.08);
            height: 6px;
            border-radius: 3px;
            outline: none;
        }

        input[type="range"]::-webkit-slider-thumb {
            -webkit-appearance: none;
            width: 16px;
            height: 16px;
            border-radius: 50%;
            background: var(--accent-color);
            cursor: pointer;
            transition: background 0.2s;
        }

        input[type="range"]::-webkit-slider-thumb:hover {
            background: var(--accent-hover);
        }

        /* Toggle switch */
        .switch {
            position: relative;
            display: inline-block;
            width: 44px;
            height: 24px;
        }

        .switch input {
            opacity: 0;
            width: 0;
            height: 0;
        }

        .slider {
            position: absolute;
            cursor: pointer;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background-color: rgba(255, 255, 255, 0.1);
            transition: .4s;
            border-radius: 24px;
        }

        .slider:before {
            position: absolute;
            content: "";
            height: 16px;
            width: 16px;
            left: 4px;
            bottom: 4px;
            background-color: white;
            transition: .4s;
            border-radius: 50%;
        }

        input:checked + .slider {
            background-color: var(--accent-color);
        }

        input:checked + .slider:before {
            transform: translateX(20px);
        }
        
        .progress-bar-container {
            width: 100%;
            height: 8px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 4px;
            overflow: hidden;
            margin-top: 10px;
        }
        
        .progress-bar-fill {
            height: 100%;
            background: var(--accent-color);
            width: 0%;
            transition: width 0.4s ease, background 0.4s;
        }
    </style>
</head>
<body>

    <header>
        <div class="logo-section">
            <h1>HR INTERVIEW AI</h1>
            <p>Independent Real-time Vision Evaluators</p>
        </div>
        <div class="status-badge">
            <div class="pulse-dot"></div>
            WEBCAM ACTIVE
        </div>
    </header>

    <main>
        <!-- Webcam View Panel -->
        <div class="card">
            <div class="video-container">
                <img src="/video_feed" class="video-feed" alt="Live Webcam Feed">
            </div>

            <div class="overall-score-panel">
                <div class="score-circle">
                    <svg viewBox="0 0 100 100">
                        <circle class="bg-circle" cx="50" cy="50" r="45"></circle>
                        <circle id="final-circle" class="val-circle" cx="50" cy="50" r="45" stroke-dasharray="283" stroke-dashoffset="283"></circle>
                    </svg>
                    <div class="score-text" id="final-percent">--%</div>
                </div>
                <div class="rating-label">
                    <p>Current Grade</p>
                    <h2 id="final-rating">CALCULATING...</h2>
                </div>
            </div>
        </div>

        <!-- Controls/Metrics Panel -->
        <div class="card controls-panel">
            <h3>Evaluation Criteria Weights & Controls</h3>
            <div id="detectors-list">
                <!-- Template populated dynamically by JavaScript -->
            </div>
        </div>
    </main>

    <script>
        const API_METRICS = '/metrics';
        const API_CONFIG = '/config';
        
        // Helper to update config on server
        async function updateServerConfig(key, changes) {
            try {
                await fetch(API_CONFIG, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        detector_key: key,
                        ...changes
                    })
                });
            } catch (err) {
                console.error("Error updating config:", err);
            }
        }

        // Generate UI row for a detector
        function createDetectorRow(key, data) {
            const label = key.replace('_', ' ').toUpperCase();
            const checked = data.enabled ? 'checked' : '';
            
            // Badge text and style
            let badgeClass = 'badge-disabled';
            let badgeText = 'Disabled';
            if (data.enabled) {
                if (data.trained) {
                    badgeClass = 'badge-trained';
                    badgeText = `Trained (${data.label})`;
                } else {
                    badgeClass = 'badge-untrained';
                    badgeText = 'Not Trained';
                }
            }
            
            return `
                <div class="detector-row" id="row-${key}">
                    <div class="detector-header">
                        <div class="detector-title">
                            <h4>${label}</h4>
                            <span class="metric-badge ${badgeClass}">${badgeText}</span>
                        </div>
                        <label class="switch">
                            <input type="checkbox" id="toggle-${key}" ${checked} onchange="toggleDetector('${key}', this.checked)">
                            <span class="slider"></span>
                        </label>
                    </div>
                    
                    <div class="slider-group">
                        <div class="slider-label">
                            <span>Contribution Weight</span>
                            <span id="weight-lbl-${key}">${Math.round(data.weight * 100)}%</span>
                        </div>
                        <input type="range" min="0" max="1" step="0.05" value="${data.weight}" 
                            oninput="updateWeightLabel('${key}', this.value)" 
                            onchange="saveWeight('${key}', this.value)">
                    </div>
                    
                    <div class="progress-bar-container">
                        <div class="progress-bar-fill" id="bar-${key}" style="width: 0%"></div>
                    </div>
                </div>
            `;
        }

        function toggleDetector(key, val) {
            updateServerConfig(key, { enabled: val });
        }

        function updateWeightLabel(key, val) {
            document.getElementById(`weight-lbl-${key}`).innerText = `${Math.round(val * 100)}%`;
        }

        function saveWeight(key, val) {
            updateServerConfig(key, { weight: parseFloat(val) });
        }

        // Main polling loop
        async function pollMetrics() {
            try {
                const response = await fetch(API_METRICS);
                const data = await response.json();
                
                // Update final score gauge
                const percent = data.final_score;
                document.getElementById('final-percent').innerText = `${percent}%`;
                document.getElementById('final-rating').innerText = data.rating;
                
                // SVG dash offset math (283 = circumference of radius 45 circle)
                const offset = 283 - (283 * percent / 100);
                document.getElementById('final-circle').style.strokeDashoffset = offset;
                
                // Update circle color based on score
                let scoreColor = 'var(--danger-color)';
                if (percent >= 85) scoreColor = 'var(--success-color)';
                else if (percent >= 70) scoreColor = 'var(--accent-color)';
                else if (percent >= 50) scoreColor = 'var(--warning-color)';
                document.getElementById('final-circle').style.stroke = scoreColor;

                // Render or update detectors list
                const listContainer = document.getElementById('detectors-list');
                const listKeys = Object.keys(data.breakdown);
                
                listKeys.forEach(key => {
                    const info = data.breakdown[key];
                    const existingRow = document.getElementById(`row-${key}`);
                    
                    if (!existingRow) {
                        // Generate row first time
                        listContainer.insertAdjacentHTML('beforeend', createDetectorRow(key, info));
                    } else {
                        // Dynamically update existing row values (avoid re-drawing to prevent slider resetting)
                        const toggle = document.getElementById(`toggle-${key}`);
                        if (toggle && document.activeElement !== toggle) {
                            toggle.checked = info.enabled;
                        }
                        
                        const wLabel = document.getElementById(`weight-lbl-${key}`);
                        if (wLabel) {
                            wLabel.innerText = `${Math.round(info.weight * 100)}%`;
                        }
                        
                        // Update score bar
                        const bar = document.getElementById(`bar-${key}`);
                        if (bar) {
                            bar.style.width = info.enabled && info.trained ? `${info.score_percent}%` : '0%';
                            // Color code status bars
                            let barColor = 'var(--danger-color)';
                            if (info.score_percent >= 85) barColor = 'var(--success-color)';
                            else if (info.score_percent >= 70) barColor = 'var(--accent-color)';
                            else if (info.score_percent >= 50) barColor = 'var(--warning-color)';
                            bar.style.backgroundColor = barColor;
                        }
                        
                        // Update status badge
                        const badge = existingRow.querySelector('.metric-badge');
                        if (badge) {
                            badge.className = 'metric-badge';
                            if (info.enabled) {
                                if (info.trained) {
                                    badge.classList.add('badge-trained');
                                    badge.innerText = `Trained (${info.label})`;
                                } else {
                                    badge.classList.add('badge-untrained');
                                    badge.innerText = 'Not Trained';
                                }
                            } else {
                                badge.classList.add('badge-disabled');
                                badge.innerText = 'Disabled';
                            }
                        }
                    }
                });

            } catch (err) {
                console.error("Error polling metrics:", err);
            }
        }

        // Poll every 300ms (fast UI updates)
        setInterval(pollMetrics, 300);
        pollMetrics();
    </script>
</body>
</html>
"""

def main():
    global detector_manager, aggregator
    print("================================================================")
    print("                 STARTING HR INTERVIEW VISION SERVER")
    print("================================================================")
    
    # Initialize background model pipelines
    detector_manager = AsyncDetectorManager()
    aggregator = HRAggregator()
    
    detector_manager.start()

    # Start capture thread
    capture_thread = threading.Thread(target=video_capture_loop, daemon=True)
    capture_thread.start()

    # Start Flask Web server
    # Running on local port 5000
    print("\n" + "=" * 60)
    print("  DASHBOARD READY!")
    print("  Open your browser and navigate to: http://127.0.0.1:5000")
    print("=" * 60 + "\n")
    
    try:
        app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
    except KeyboardInterrupt:
        print("\nStopping vision server...")
    finally:
        detector_manager.stop()

if __name__ == "__main__":
    main()
