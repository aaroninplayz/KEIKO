/* ============================================================
   KEIKO — Admin / Trainer Portal
   ============================================================ */

(() => {
  'use strict';

  // ── Configuration ──────────────────────────────────────────
  const CONFIG = {
    WS_BASE: location.protocol === 'https:' ? 'wss://' : 'ws://',
    WS_HOST: location.host || 'localhost:8000',
    WS_PATH: '/api/v1/interview/ws/',
    CAPTURE_FPS: 10,
    JPEG_QUALITY: 0.5,
    RECONNECT_BASE_DELAY: 1000,
    RECONNECT_MAX_DELAY: 15000,
    LERP_SPEED: 0.08,
    DEFAULT_WEIGHTS: { posture: 30, eye: 25, body: 20, attire: 15, confidence: 10 },
  };

  // ── State ──────────────────────────────────────────────────
  const state = {
    sessionId: generateSessionId(),
    ws: null,
    connected: false,
    reconnectAttempts: 0,
    reconnectTimer: null,
    captureInterval: null,
    stream: null,
    startTime: Date.now(),
    frameCount: 0,
    durationTimer: null,

    // Displayed (lerped) values
    display: { overall: 0, posture: 0, eye: 0, body: 0, attire: 0 },
    // Target values from server
    target:  { overall: 0, posture: 0, eye: 0, body: 0, attire: 0 },
    // Weights
    weights: { ...CONFIG.DEFAULT_WEIGHTS },
    // Latest raw data
    rawData: null,
    landmarkData: null,
    // Sub-scores
    sub: {
      spine: 0, shoulder: 0, headTilt: 0, lean: 0,
      gazeRatio: 0, blinkRate: 0, pupilStability: 0, focusDuration: 0,
      gesture: 0, openness: 0, fidget: 0, energy: 0,
      formality: 0, neatness: 0, colorAppropriate: 0,
    },
    animating: false,
  };

  // ── DOM ────────────────────────────────────────────────────
  const $ = (sel) => document.querySelector(sel);
  const dom = {
    videoEl:        $('#adminVideoEl'),
    captureCanvas:  $('#adminCaptureCanvas'),
    liveBadge:      $('#adminLiveBadge'),
    sessionId:      $('#adminSessionId'),
    connStatus:     $('#adminConnStatus'),
    connLabel:      $('#adminConnLabel'),
    sessionInput:   $('#adminSessionInput'),
    joinBtn:        $('#adminJoinBtn'),
    newSessionBtn:  $('#adminNewSessionBtn'),
    duration:       $('#adminDuration'),
    frameCount:     $('#adminFrameCount'),

    // Overall preview
    gaugeOverall:   $('#adminGaugeOverall'),
    valOverall:     $('#adminValOverall'),
    weightedSum:    $('#adminWeightedSum'),
    totalWeight:    $('#adminTotalWeight'),
    normalized:     $('#adminNormalized'),

    // Metric values
    valPosture:     $('#adminValPosture'),
    barPosture:     $('#adminBarPosture'),
    valEye:         $('#adminValEye'),
    barEye:         $('#adminBarEye'),
    valBody:        $('#adminValBody'),
    barBody:        $('#adminBarBody'),
    valAttire:      $('#adminValAttire'),
    barAttire:      $('#adminBarAttire'),

    // Sub-scores
    subSpine:       $('#subSpine'),
    subShoulder:    $('#subShoulder'),
    subHeadTilt:    $('#subHeadTilt'),
    subLean:        $('#subLean'),
    subGazeRatio:   $('#subGazeRatio'),
    subBlinkRate:   $('#subBlinkRate'),
    subPupilStability: $('#subPupilStability'),
    subFocusDuration:  $('#subFocusDuration'),
    subGesture:     $('#subGesture'),
    subOpenness:    $('#subOpenness'),
    subFidget:      $('#subFidget'),
    subEnergy:      $('#subEnergy'),
    subFormality:   $('#subFormality'),
    subNeatness:    $('#subNeatness'),
    subColor:       $('#subColor'),

    // Weights
    awPosture:      $('#awPosture'),
    awPostureVal:   $('#awPostureVal'),
    awPostureFill:  $('#awPostureFill'),
    awEye:          $('#awEye'),
    awEyeVal:       $('#awEyeVal'),
    awEyeFill:      $('#awEyeFill'),
    awBody:         $('#awBody'),
    awBodyVal:      $('#awBodyVal'),
    awBodyFill:     $('#awBodyFill'),
    awAttire:       $('#awAttire'),
    awAttireVal:    $('#awAttireVal'),
    awAttireFill:   $('#awAttireFill'),
    awConfidence:   $('#awConfidence'),
    awConfidenceVal:$('#awConfidenceVal'),
    awConfidenceFill:$('#awConfidenceFill'),
    awResetBtn:     $('#awResetBtn'),
    awPushBtn:      $('#awPushBtn'),

    // Raw data
    rawJsonToggle:  $('#rawJsonToggle'),
    rawJsonCollapsible: $('#rawJsonCollapsible'),
    rawJsonViewer:  $('#rawJsonViewer'),
    landmarkToggle: $('#landmarkToggle'),
    landmarkCollapsible: $('#landmarkCollapsible'),
    landmarkViewer: $('#landmarkViewer'),
  };

  // ── Utilities ──────────────────────────────────────────────
  function generateSessionId() {
    try {
      if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
        return 'sess_' + crypto.randomUUID().split('-').slice(0, 2).join('');
      }
    } catch (e) {}
    // Context-independent random fallback
    return 'sess_' + Math.random().toString(36).substring(2, 10);
  }

  function clamp(v, lo = 0, hi = 100) {
    return Math.max(lo, Math.min(hi, v));
  }

  function lerp(current, target, t) {
    return current + (target - current) * t;
  }

  function scoreColorHex(val) {
    if (val > 70) return 'var(--secondary)';
    if (val >= 40) return 'var(--warning)';
    return 'var(--tertiary-container)';
  }

  function scoreColorClass(val) {
    if (val > 70) return 'metric-card__value--green';
    if (val >= 40) return 'metric-card__value--yellow';
    return 'metric-card__value--red';
  }

  function formatDuration(ms) {
    const s = Math.floor(ms / 1000);
    const m = Math.floor(s / 60);
    const h = Math.floor(m / 60);
    if (h > 0) return `${h}:${String(m % 60).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
    return `${String(m).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
  }

  // ── Gauge Helpers ──────────────────────────────────────────
  const CIRCUMFERENCE_OVERALL = 2 * Math.PI * 68; // ≈427.26

  function setCircleGauge(el, circ, pct) {
    el.style.strokeDashoffset = circ * (1 - pct / 100);
  }

  // ── JSON Syntax Highlighting ───────────────────────────────
  function syntaxHighlight(json) {
    if (typeof json !== 'string') json = JSON.stringify(json, null, 2);
    return json.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"(\\u[a-fA-F0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?/g, (match) => {
        let cls = 'json-string';
        if (match.endsWith(':')) {
          cls = 'json-key';
          return `<span class="${cls}">${match}</span>`;
        }
        return `<span class="${cls}">${match}</span>`;
      })
      .replace(/\b(-?\d+\.?\d*([eE][+-]?\d+)?)\b/g, '<span class="json-number">$1</span>')
      .replace(/\b(true|false)\b/g, '<span class="json-bool">$1</span>')
      .replace(/\bnull\b/g, '<span class="json-null">null</span>');
  }

  // ── Recalculate Overall (Preview) ─────────────────────────
  function recalcPreview() {
    const w = state.weights;
    const d = state.display;
    const totalWeight = w.posture + w.eye + w.body + w.attire + w.confidence;
    const weightedSum =
      (d.posture * w.posture) +
      (d.eye * w.eye) +
      (d.body * w.body) +
      (d.attire * w.attire) +
      (d.overall * w.confidence); // confidence acts as a bonus multiplier

    const normalized = totalWeight > 0 ? weightedSum / totalWeight : 0;

    dom.weightedSum.textContent = weightedSum.toFixed(1);
    dom.totalWeight.textContent = totalWeight;
    dom.normalized.textContent = normalized.toFixed(1);

    return normalized;
  }

  // ── Animation Loop ─────────────────────────────────────────
  function startAnimationLoop() {
    if (state.animating) return;
    state.animating = true;
    requestAnimationFrame(animationTick);
  }

  function animationTick() {
    const d = state.display;
    const t = state.target;
    let needsUpdate = false;

    for (const key of ['overall', 'posture', 'eye', 'body', 'attire']) {
      if (Math.abs(d[key] - t[key]) > 0.2) {
        d[key] = lerp(d[key], t[key], CONFIG.LERP_SPEED);
        needsUpdate = true;
      } else {
        d[key] = t[key];
      }
    }

    renderMetrics();

    if (needsUpdate) {
      requestAnimationFrame(animationTick);
    } else {
      state.animating = false;
    }
  }

  // ── Render ─────────────────────────────────────────────────
  function renderMetrics() {
    const d = state.display;

    // Overall gauge
    const ov = Math.round(d.overall);
    dom.valOverall.textContent = ov;
    setCircleGauge(dom.gaugeOverall, CIRCUMFERENCE_OVERALL, d.overall);
    dom.gaugeOverall.style.stroke = scoreColorHex(d.overall);

    // Posture
    const ps = Math.round(d.posture);
    dom.valPosture.textContent = ps;
    dom.valPosture.className = `metric-card__value ${scoreColorClass(d.posture)}`;
    dom.barPosture.style.width = d.posture + '%';
    dom.barPosture.style.background = scoreColorHex(d.posture);

    // Eye Contact
    const ey = Math.round(d.eye);
    dom.valEye.textContent = ey;
    dom.valEye.className = `metric-card__value ${scoreColorClass(d.eye)}`;
    dom.barEye.style.width = d.eye + '%';
    dom.barEye.style.background = scoreColorHex(d.eye);

    // Body Language
    const bd = Math.round(d.body);
    dom.valBody.textContent = bd;
    dom.valBody.className = `metric-card__value ${scoreColorClass(d.body)}`;
    dom.barBody.style.width = d.body + '%';
    dom.barBody.style.background = scoreColorHex(d.body);

    // Attire
    const at = Math.round(d.attire);
    dom.valAttire.textContent = at;
    dom.valAttire.className = `metric-card__value ${scoreColorClass(d.attire)}`;
    dom.barAttire.style.width = d.attire + '%';
    dom.barAttire.style.background = scoreColorHex(d.attire);

    // Sub-scores
    const s = state.sub;
    dom.subSpine.textContent = s.spine.toFixed(1);
    dom.subShoulder.textContent = s.shoulder.toFixed(1);
    dom.subHeadTilt.textContent = s.headTilt.toFixed(1) + '°';
    dom.subLean.textContent = s.lean.toFixed(1) + '°';
    dom.subGazeRatio.textContent = s.gazeRatio.toFixed(1) + '%';
    dom.subBlinkRate.textContent = s.blinkRate.toFixed(1) + '/min';
    dom.subPupilStability.textContent = s.pupilStability.toFixed(1);
    dom.subFocusDuration.textContent = s.focusDuration.toFixed(1) + 's';
    dom.subGesture.textContent = s.gesture.toFixed(1);
    dom.subOpenness.textContent = s.openness.toFixed(1);
    dom.subFidget.textContent = s.fidget.toFixed(1);
    dom.subEnergy.textContent = s.energy.toFixed(1);
    dom.subFormality.textContent = s.formality.toFixed(1);
    dom.subNeatness.textContent = s.neatness.toFixed(1);
    dom.subColor.textContent = s.colorAppropriate.toFixed(1);

    // Preview recalculation
    recalcPreview();
  }

  // ── Camera ─────────────────────────────────────────────────
  async function initCamera() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' },
        audio: false,
      });
      state.stream = stream;
      dom.videoEl.srcObject = stream;
      dom.liveBadge.style.display = 'flex';
      startFrameCapture();
    } catch (err) {
      console.error('[Keiko Admin] Camera access denied:', err);
    }
  }

  function startFrameCapture() {
    if (state.captureTimeout) clearTimeout(state.captureTimeout);
    state.waitingForFrameAck = false;
    state.lastFrameTime = 0;
    captureAndSendLoop();
  }

  function captureAndSendLoop() {
    if (!state.connected || !state.stream) {
      state.captureTimeout = setTimeout(captureAndSendLoop, 500);
      return;
    }
    
    // Safety: if waiting for ack > 2s, force-release the lock
    if (state.waitingForFrameAck && (Date.now() - state.lastFrameTime > 2000)) {
      console.warn('[Keiko Admin] Frame acknowledgement timed out, resetting lock');
      state.waitingForFrameAck = false;
    }

    if (!state.waitingForFrameAck) {
      captureAndSend();
    }
    
    state.captureTimeout = setTimeout(captureAndSendLoop, 100);
  }

  function captureAndSend() {
    if (!state.connected || !state.stream) return;

    const video = dom.videoEl;
    const canvas = dom.captureCanvas;
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;

    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    const base64 = canvas.toDataURL('image/jpeg', CONFIG.JPEG_QUALITY).split(',')[1];
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
      state.waitingForFrameAck = true;
      state.lastFrameTime = Date.now();
      state.ws.send(JSON.stringify({ type: 'video_frame', data: base64 }));
      state.frameCount++;
      dom.frameCount.textContent = state.frameCount;
    }
  }

  // ── WebSocket ──────────────────────────────────────────────
  function connectWS() {
    if (state.ws) {
      state.ws.onclose = null;
      state.ws.close();
    }

    const url = CONFIG.WS_BASE + CONFIG.WS_HOST + CONFIG.WS_PATH + state.sessionId;
    console.log('[Keiko Admin] Connecting to', url);
    setConnectionStatus('reconnecting');

    const ws = new WebSocket(url);
    state.ws = ws;

    ws.onopen = () => {
      console.log('[Keiko Admin] Connected');
      state.connected = true;
      state.reconnectAttempts = 0;
      setConnectionStatus('connected');
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        handleMessage(msg);
      } catch (e) {
        console.warn('[Keiko Admin] Bad message:', e);
      }
    };

    ws.onerror = (err) => console.error('[Keiko Admin] WS error:', err);

    ws.onclose = () => {
      state.connected = false;
      setConnectionStatus('disconnected');
      scheduleReconnect();
    };
  }

  function scheduleReconnect() {
    if (state.reconnectTimer) clearTimeout(state.reconnectTimer);
    const delay = Math.min(
      CONFIG.RECONNECT_BASE_DELAY * Math.pow(2, state.reconnectAttempts),
      CONFIG.RECONNECT_MAX_DELAY
    );
    state.reconnectAttempts++;
    state.reconnectTimer = setTimeout(connectWS, delay);
  }

  function setConnectionStatus(status) {
    dom.connStatus.className = 'connection-status connection-status--' + status;
    const labels = { connected: 'Connected', disconnected: 'Disconnected', reconnecting: 'Reconnecting…' };
    dom.connLabel.textContent = labels[status] || status;
  }

  // ── Message Handling ───────────────────────────────────────
  function handleMessage(msg) {
    // Store raw data for JSON viewer
    state.rawData = msg;
    updateRawJsonViewer(msg);

    if (msg.type === 'metrics_update') {
      // Clear backpressure flag
      state.waitingForFrameAck = false;

      const sensors = msg.sensors || {};

      // Overall weighted score
      if (msg.weighted_overall !== undefined) {
        state.target.overall = clamp(msg.weighted_overall);
      }

      // Individual sensor scores
      if (sensors.posture && sensors.posture.score !== undefined) {
        state.target.posture = clamp(sensors.posture.score);
      }
      if (sensors.eye_contact && sensors.eye_contact.score !== undefined) {
        state.target.eye = clamp(sensors.eye_contact.score);
      }
      if (sensors.body_language && sensors.body_language.score !== undefined) {
        state.target.body = clamp(sensors.body_language.score);
      }
      if (sensors.attire && sensors.attire.score !== undefined) {
        state.target.attire = clamp(sensors.attire.score);
      }

      // Posture sub-scores from details
      const pDetails = (sensors.posture || {}).details || {};
      if (pDetails.spine_score !== undefined) state.sub.spine = pDetails.spine_score;
      if (pDetails.shoulder_alignment !== undefined) state.sub.shoulder = pDetails.shoulder_alignment;
      if (pDetails.head_alignment !== undefined) state.sub.headTilt = pDetails.head_alignment;
      if (pDetails.spine_angle !== undefined) state.sub.lean = pDetails.spine_angle;

      // Eye contact sub-scores from details
      const eDetails = (sensors.eye_contact || {}).details || {};
      if (eDetails.horizontal_ratio !== undefined) state.sub.gazeRatio = eDetails.horizontal_ratio * 100;
      if (eDetails.deviation !== undefined) state.sub.blinkRate = eDetails.deviation;
      if (eDetails.raw_score !== undefined) state.sub.pupilStability = eDetails.raw_score;
      if (eDetails.is_making_contact !== undefined) state.sub.focusDuration = eDetails.is_making_contact ? 1.0 : 0.0;

      // Body language sub-scores from details
      const bDetails = (sensors.body_language || {}).details || {};
      if (bDetails.gesture_activity !== undefined) state.sub.gesture = bDetails.gesture_activity;
      if (bDetails.openness !== undefined) state.sub.openness = bDetails.openness;
      if (bDetails.hand_activity_raw !== undefined) state.sub.fidget = bDetails.hand_activity_raw * 1000; // scale for display
      if (bDetails.head_engagement !== undefined) state.sub.energy = bDetails.head_engagement;

      // Attire sub-scores from details
      const aDetails = (sensors.attire || {}).details || {};
      if (aDetails.saturation_uniformity !== undefined) state.sub.formality = aDetails.saturation_uniformity;
      if (aDetails.brightness_consistency !== undefined) state.sub.neatness = aDetails.brightness_consistency;
      if (aDetails.color_simplicity !== undefined) state.sub.colorAppropriate = aDetails.color_simplicity;

      startAnimationLoop();
    }

    if (msg.type === 'connected') {
      console.log('[Keiko Admin] Server confirmed session:', msg.session_id);
      if (msg.weights) {
        applyWeights(msg.weights);
      }
    }

    if (msg.type === 'weights_updated') {
      if (msg.weights) {
        applyWeights(msg.weights);
      }
    }

    if (msg.type === 'frame_ack') {
      // Server acknowledged a throttled frame
      state.waitingForFrameAck = false;
      return;
    }

    if (msg.type === 'error') {
      console.warn('[Keiko Admin] Server error:', msg.message);
      state.waitingForFrameAck = false;
    }
  }

  function applyWeights(w) {
    const keyMap = {
      posture: 'posture',
      eye_contact: 'eye',
      body_language: 'body',
      attire: 'attire',
      confidence: 'confidence',
    };
    for (const [serverKey, localKey] of Object.entries(keyMap)) {
      if (w[serverKey] !== undefined) {
        const val = Math.round(w[serverKey] * 100);
        state.weights[localKey] = val;
        syncSlider(localKey, val);
      }
    }
  }

  function updateRawJsonViewer(data) {
    dom.rawJsonViewer.innerHTML = syntaxHighlight(data);
  }

  function updateLandmarkViewer(data) {
    dom.landmarkViewer.innerHTML = syntaxHighlight(data);
  }

  // ── Slider Setup ───────────────────────────────────────────
  const SLIDER_NAMES = ['Posture', 'Eye', 'Body', 'Attire', 'Confidence'];
  const SLIDER_KEYS  = ['posture', 'eye', 'body', 'attire', 'confidence'];

  function setupSlider(name, key) {
    const slider = dom['aw' + name];
    const valEl  = dom['aw' + name + 'Val'];
    const fillEl = dom['aw' + name + 'Fill'];

    slider.addEventListener('input', () => {
      const v = parseInt(slider.value, 10);
      valEl.textContent = v;
      fillEl.style.width = v + '%';
      state.weights[key] = v;
      recalcPreview();
    });
  }

  function syncSlider(key, value) {
    const name = key.charAt(0).toUpperCase() + key.slice(1);
    const slider = dom['aw' + name];
    const valEl  = dom['aw' + name + 'Val'];
    const fillEl = dom['aw' + name + 'Fill'];
    if (slider) slider.value = value;
    if (valEl)  valEl.textContent = value;
    if (fillEl) fillEl.style.width = value + '%';
  }

  function pushWeights() {
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
      state.ws.send(JSON.stringify({
        type: 'update_weights',
        weights: { ...state.weights },
      }));
    }
  }

  function resetWeights() {
    state.weights = { ...CONFIG.DEFAULT_WEIGHTS };
    for (let i = 0; i < SLIDER_NAMES.length; i++) {
      syncSlider(SLIDER_KEYS[i], state.weights[SLIDER_KEYS[i]]);
    }
    recalcPreview();
  }

  // ── Collapsibles ───────────────────────────────────────────
  function toggleCollapsible(el) {
    el.classList.toggle('collapsible--open');
  }

  // ── Session Management ─────────────────────────────────────
  function joinSession() {
    const id = dom.sessionInput.value.trim();
    if (!id) return;
    state.sessionId = id;
    dom.sessionId.textContent = id;
    state.frameCount = 0;
    state.startTime = Date.now();
    connectWS();
  }

  function newSession() {
    state.sessionId = generateSessionId();
    dom.sessionId.textContent = state.sessionId;
    dom.sessionInput.value = '';
    state.frameCount = 0;
    state.startTime = Date.now();
    connectWS();
  }

  // ── Duration Timer ─────────────────────────────────────────
  function startDurationTimer() {
    state.durationTimer = setInterval(() => {
      const elapsed = Date.now() - state.startTime;
      dom.duration.textContent = formatDuration(elapsed);
    }, 1000);
  }

  // ── Event Binding ──────────────────────────────────────────
  function bindEvents() {
    // Sliders
    for (let i = 0; i < SLIDER_NAMES.length; i++) {
      setupSlider(SLIDER_NAMES[i], SLIDER_KEYS[i]);
    }

    dom.awPushBtn.addEventListener('click', pushWeights);
    dom.awResetBtn.addEventListener('click', resetWeights);

    // Collapsibles
    dom.rawJsonToggle.addEventListener('click', () => toggleCollapsible(dom.rawJsonCollapsible));
    dom.landmarkToggle.addEventListener('click', () => toggleCollapsible(dom.landmarkCollapsible));

    // Session
    dom.joinBtn.addEventListener('click', joinSession);
    dom.newSessionBtn.addEventListener('click', newSession);
    dom.sessionInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') joinSession();
    });
  }

  // ── Init ───────────────────────────────────────────────────
  function init() {
    dom.sessionId.textContent = state.sessionId;
    bindEvents();
    initCamera();
    connectWS();
    startDurationTimer();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
