/* ============================================================
   KEIKO — Main Dashboard Application
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
    LERP_SPEED: 0.08, // per-frame interpolation factor
  };

  // ── State ──────────────────────────────────────────────────
  const state = {
    sessionId: resolveSessionId(),
    ws: null,
    connected: false,
    reconnectAttempts: 0,
    reconnectTimer: null,
    captureInterval: null,
    isFullscreen: false,
    stream: null,
    // Current displayed (lerped) values
    display: { overall: 0, posture: 0, eye: 0, body: 0, attire: 0 },
    // Target values from server
    target:  { overall: 0, posture: 0, eye: 0, body: 0, attire: 0 },
    // Sub-scores
    sub: { eyeGaze: 0, eyeBlink: 0 },
    // Weights
    weights: { posture: 30, eye: 30, body: 25, attire: 15 },
    animating: false,
    isRecording: false,
    audioStream: null,
  };

  // ── DOM Elements ───────────────────────────────────────────
  const $ = (sel) => document.querySelector(sel);
  const dom = {
    dashboard:    $('#dashboard'),
    videoEl:      $('#videoEl'),
    videoContainer: $('#videoContainer'),
    captureCanvas: $('#captureCanvas'),
    liveBadge:    $('#liveBadge'),
    sessionId:    $('#sessionId'),

    // Connection
    connStatus:   $('#connectionStatus'),
    connLabel:    $('#connectionLabel'),

    // Gauges & values
    gaugeOverall: $('#gaugeOverall'),
    valOverall:   $('#valOverall'),
    subOverall:   $('#subOverall'),
    cardOverall:  $('#cardOverall'),

    gaugePosture: $('#gaugePosture'),
    valPosture:   $('#valPosture'),

    gaugeEye:     $('#gaugeEye'),
    valEye:       $('#valEye'),
    valEyeRing:   $('#valEyeRing'),
    subEyeGaze:   $('#subEyeGaze'),
    subEyeBlink:  $('#subEyeBlink'),

    barBody:      $('#barBody'),
    valBody:      $('#valBody'),

    barAttire:    $('#barAttire'),
    valAttire:    $('#valAttire'),

    // Fullscreen
    fullscreenBtn: $('#fullscreenBtn'),
    fsIconExpand:  $('#fsIconExpand'),
    fsIconCompress:$('#fsIconCompress'),

    // Settings modal
    settingsBtn:  $('#settingsBtn'),
    modalOverlay: $('#modalOverlay'),
    modalClose:   $('#modalClose'),
    modalCancel:  $('#modalCancel'),
    modalSave:    $('#modalSave'),

    // Weight sliders
    wPosture:     $('#wPosture'),
    wPostureVal:  $('#wPostureVal'),
    wPostureFill: $('#wPostureFill'),
    wEye:         $('#wEye'),
    wEyeVal:      $('#wEyeVal'),
    wEyeFill:     $('#wEyeFill'),
    wBody:        $('#wBody'),
    wBodyVal:     $('#wBodyVal'),
    wBodyFill:    $('#wBodyFill'),
    wAttire:      $('#wAttire'),
    wAttireVal:   $('#wAttireVal'),
    wAttireFill:  $('#wAttireFill'),

    // Candidate Workspace elements
    resumeDropzone: $('#resumeDropzone'),
    resumeFileInput: $('#resumeFileInput'),
    resumeStatus: $('#resumeStatus'),
    jdTextarea: $('#jdTextarea'),
    analyzeJdBtn: $('#analyzeJdBtn'),
    jdStatus: $('#jdStatus'),
    matchResultsPanel: $('#matchResultsPanel'),
    alignmentScoreBadge: $('#alignmentScoreBadge'),
    matchExpPercent: $('#matchExpPercent'),
    matchSkillsPercent: $('#matchSkillsPercent'),
    strengthsList: $('#strengthsList'),
    gapTagsList: $('#gapTagsList'),
    skillsTagsList: $('#skillsTagsList'),

    // Interview UI
    startInterviewBtn: $('#startInterviewBtn'),
    questionIndexLabel: $('#questionIndexLabel'),
    questionDisplayContainer: $('#questionDisplayContainer'),
    questionText: $('#questionText'),
    recordingControls: $('#recordingControls'),
    recordBtn: $('#recordBtn'),
    recordingStatusLabel: $('#recordingStatusLabel'),
    submitAnswerBtn: $('#submitAnswerBtn'),
    textAnswerContainer: $('#textAnswerContainer'),
    textAnswerInput: $('#textAnswerInput'),
  };

  // ── Utilities ──────────────────────────────────────────────
  function resolveSessionId() {
    try {
      const urlParams = new URLSearchParams(window.location.search);
      const urlSessionId = urlParams.get('session_id');
      if (urlSessionId && urlSessionId.trim() !== '') {
        console.log('[Keiko] Resolved session_id from URL:', urlSessionId.trim());
        return urlSessionId.trim();
      }
    } catch (e) {
      console.warn('[Keiko] Could not parse URL query parameters:', e);
    }
    return generateSessionId();
  }

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

  function scoreColor(val) {
    if (val > 70) return 'green';
    if (val >= 40) return 'yellow';
    return 'red';
  }

  function scoreColorHex(val) {
    if (val > 70) return 'var(--secondary)';
    if (val >= 40) return 'var(--warning)';
    return 'var(--tertiary-container)';
  }

  // ── Gauge Helpers ──────────────────────────────────────────
  // Full circle circumference for overall: 2 * π * 68 ≈ 427.26
  const CIRCUMFERENCE_OVERALL = 2 * Math.PI * 68;
  // Semicircle arc length for posture: π * 60 ≈ 188.50
  const ARC_LENGTH_POSTURE = Math.PI * 60;
  // Full circle for eye ring: 2 * π * 42 ≈ 263.89
  const CIRCUMFERENCE_EYE = 2 * Math.PI * 42;

  function setCircleGauge(el, circumference, pct) {
    const offset = circumference * (1 - pct / 100);
    el.style.strokeDashoffset = offset;
  }

  function setArcGauge(el, arcLen, pct) {
    const offset = arcLen * (1 - pct / 100);
    el.style.strokeDashoffset = offset;
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

    // Overall
    const ov = Math.round(d.overall);
    dom.valOverall.textContent = ov;
    setCircleGauge(dom.gaugeOverall, CIRCUMFERENCE_OVERALL, d.overall);
    dom.gaugeOverall.style.stroke = scoreColorHex(d.overall);
    dom.valOverall.className = 'gauge-center-label__value';

    // Update hero card glow
    const ovCard = dom.cardOverall;
    ovCard.classList.remove('glass-panel--active', 'glass-panel--secondary', 'glass-panel--danger');
    if (d.overall > 70) ovCard.classList.add('glass-panel--secondary');
    else if (d.overall >= 40) ovCard.classList.add('glass-panel--active');
    else ovCard.classList.add('glass-panel--danger');

    dom.subOverall.textContent = getOverallDescription(d.overall);

    // Posture
    const ps = Math.round(d.posture);
    dom.valPosture.textContent = ps;
    dom.valPosture.className = `metric-card__value metric-card__value--${scoreColor(d.posture)}`;
    setArcGauge(dom.gaugePosture, ARC_LENGTH_POSTURE, d.posture);
    dom.gaugePosture.style.stroke = scoreColorHex(d.posture);

    // Eye Contact
    const ey = Math.round(d.eye);
    dom.valEye.textContent = ey;
    dom.valEye.className = `metric-card__value metric-card__value--${scoreColor(d.eye)}`;
    dom.valEyeRing.textContent = ey;
    setCircleGauge(dom.gaugeEye, CIRCUMFERENCE_EYE, d.eye);
    dom.gaugeEye.style.stroke = scoreColorHex(d.eye);

    // Sub-scores
    dom.subEyeGaze.textContent = state.sub.eyeGaze.toFixed(1) + '%';
    dom.subEyeBlink.textContent = state.sub.eyeBlink.toFixed(1);

    // Body Language
    const bd = Math.round(d.body);
    dom.valBody.textContent = bd;
    dom.valBody.className = `metric-card__value metric-card__value--${scoreColor(d.body)}`;
    dom.barBody.style.width = d.body + '%';
    dom.barBody.style.background = scoreColorHex(d.body);

    // Attire
    const at = Math.round(d.attire);
    dom.valAttire.textContent = at;
    dom.valAttire.className = `metric-card__value metric-card__value--${scoreColor(d.attire)}`;
    dom.barAttire.style.width = d.attire + '%';
    dom.barAttire.style.background = scoreColorHex(d.attire);
  }

  function getOverallDescription(val) {
    if (val >= 85) return 'Exceptional — Interview ready';
    if (val >= 70) return 'Strong performance';
    if (val >= 55) return 'Room for improvement';
    if (val >= 40) return 'Needs attention';
    return 'Significant gaps detected';
  }

  // ── Camera ─────────────────────────────────────────────────
  async function initCamera() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' },
        audio: true,
      });
      state.stream = stream;
      dom.videoEl.srcObject = stream;
      dom.liveBadge.style.display = 'flex';
      startFrameCapture();
    } catch (err) {
      console.error('[Keiko] Camera access denied:', err);
      dom.liveBadge.style.display = 'none';
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
    
    // Safety: if we have been waiting for acknowledgement for > 2 seconds, force-release the lock
    if (state.waitingForFrameAck && (Date.now() - state.lastFrameTime > 2000)) {
      console.warn('[Keiko] Frame acknowledgement timed out, resetting lock');
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

    const dataUrl = canvas.toDataURL('image/jpeg', CONFIG.JPEG_QUALITY);
    const base64 = dataUrl.split(',')[1];

    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
      state.waitingForFrameAck = true;
      state.lastFrameTime = Date.now();
      state.ws.send(JSON.stringify({
        type: 'video_frame',
        data: base64,
      }));
    }
  }

  // ── WebSocket ──────────────────────────────────────────────
  function connectWS() {
    const url = CONFIG.WS_BASE + CONFIG.WS_HOST + CONFIG.WS_PATH + state.sessionId;
    console.log('[Keiko] Connecting to', url);
    setConnectionStatus('reconnecting');

    const ws = new WebSocket(url);
    state.ws = ws;

    ws.onopen = () => {
      console.log('[Keiko] WebSocket connected');
      state.connected = true;
      state.reconnectAttempts = 0;
      setConnectionStatus('connected');
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        handleMessage(msg);
      } catch (e) {
        console.warn('[Keiko] Bad message:', e);
      }
    };

    ws.onerror = (err) => {
      console.error('[Keiko] WebSocket error:', err);
    };

    ws.onclose = (event) => {
      console.log('[Keiko] WebSocket closed:', event.code, event.reason);
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
    console.log(`[Keiko] Reconnecting in ${delay}ms (attempt ${state.reconnectAttempts})`);
    state.reconnectTimer = setTimeout(connectWS, delay);
  }

  function setConnectionStatus(status) {
    dom.connStatus.className = 'connection-status connection-status--' + status;
    const labels = { connected: 'Connected', disconnected: 'Disconnected', reconnecting: 'Reconnecting…' };
    dom.connLabel.textContent = labels[status] || status;
  }

  // ── Message Handling ───────────────────────────────────────
  function handleMessage(msg) {
    if (msg.type === 'metrics_update') {
      // Clear backpressure flag — server processed our frame
      state.waitingForFrameAck = false;

      const sensors = msg.sensors || {};
      
      // Overall weighted score
      if (msg.weighted_overall !== undefined) {
        state.target.overall = clamp(msg.weighted_overall);
      }

      // Individual sensor scores — server sends {posture: {score: X, details: {...}}, ...}
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

      // Sub-scores from eye_contact details
      const eyeDetails = (sensors.eye_contact || {}).details || {};
      if (eyeDetails.horizontal_ratio !== undefined) {
        state.sub.eyeGaze = eyeDetails.horizontal_ratio * 100;  // normalize 0-1 to 0-100
      }
      if (eyeDetails.deviation !== undefined) {
        state.sub.eyeBlink = eyeDetails.deviation;
      }

      startAnimationLoop();
    }

    if (msg.type === 'connected') {
      console.log('[Keiko] Server confirmed session:', msg.session_id);
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
      // Server acknowledged a throttled frame — release backpressure
      state.waitingForFrameAck = false;
      return;
    }

    if (msg.type === 'error') {
      console.warn('[Keiko] Server error:', msg.message);
      state.waitingForFrameAck = false;
    }

    if (msg.type === 'new_question') {
      if (dom.questionText) dom.questionText.textContent = msg.question;
      if (dom.questionIndexLabel) dom.questionIndexLabel.textContent = `Question ${msg.index + 1} / 3`;
      if (dom.recordingStatusLabel) {
        dom.recordingStatusLabel.textContent = 'Ready for answer';
        dom.recordingStatusLabel.style.color = 'var(--text-muted)';
      }
    }

    if (msg.type === 'interview_complete') {
      if (dom.questionText) dom.questionText.textContent = "Interview Completed! Generating final report...";
      if (dom.questionIndexLabel) dom.questionIndexLabel.textContent = "Completed";
      if (dom.recordingControls) dom.recordingControls.style.display = 'none';
      if (dom.textAnswerContainer) dom.textAnswerContainer.style.display = 'none';
      
      const overallScore = msg.report ? msg.report.overall_score : 0;
      alert(`Interview Completed! Overall assessment score: ${overallScore}%`);
    }
  }

  function applyWeights(w) {
    if (w.posture !== undefined) { state.weights.posture = Math.round(w.posture * 100); syncSlider('Posture', state.weights.posture); }
    if (w.eye_contact !== undefined) { state.weights.eye = Math.round(w.eye_contact * 100); syncSlider('Eye', state.weights.eye); }
    if (w.body_language !== undefined) { state.weights.body = Math.round(w.body_language * 100); syncSlider('Body', state.weights.body); }
    if (w.attire !== undefined) { state.weights.attire = Math.round(w.attire * 100); syncSlider('Attire', state.weights.attire); }
  }

  // ── Fullscreen ─────────────────────────────────────────────
  function toggleFullscreen() {
    if (!document.fullscreenElement) {
      dom.dashboard.requestFullscreen().then(() => {
        state.isFullscreen = true;
        dom.dashboard.classList.add('fullscreen-mode');
        dom.fsIconExpand.style.display = 'none';
        dom.fsIconCompress.style.display = 'block';
      }).catch(console.error);
    } else {
      document.exitFullscreen().then(() => {
        state.isFullscreen = false;
        dom.dashboard.classList.remove('fullscreen-mode');
        dom.fsIconExpand.style.display = 'block';
        dom.fsIconCompress.style.display = 'none';
      }).catch(console.error);
    }
  }

  document.addEventListener('fullscreenchange', () => {
    if (!document.fullscreenElement) {
      state.isFullscreen = false;
      dom.dashboard.classList.remove('fullscreen-mode');
      dom.fsIconExpand.style.display = 'block';
      dom.fsIconCompress.style.display = 'none';
    }
  });

  // ── Settings Modal ─────────────────────────────────────────
  function openModal() {
    dom.modalOverlay.classList.add('modal-overlay--open');
  }

  function closeModal() {
    dom.modalOverlay.classList.remove('modal-overlay--open');
  }

  // Slider value sync
  function setupSlider(name) {
    const slider = dom['w' + name];
    const valEl  = dom['w' + name + 'Val'];
    const fillEl = dom['w' + name + 'Fill'];

    slider.addEventListener('input', () => {
      const v = slider.value;
      valEl.textContent = (v / 100).toFixed(2);
      fillEl.style.width = v + '%';
    });
  }

  function syncSlider(name, value) {
    const slider = dom['w' + name];
    const valEl  = dom['w' + name + 'Val'];
    const fillEl = dom['w' + name + 'Fill'];
    if (slider) { slider.value = value; }
    if (valEl)  { valEl.textContent = (value / 100).toFixed(2); }
    if (fillEl) { fillEl.style.width = value + '%'; }
  }

  function saveWeights() {
    const weights = {
      posture:    parseInt(dom.wPosture.value, 10),
      eye:        parseInt(dom.wEye.value, 10),
      body:       parseInt(dom.wBody.value, 10),
      attire:     parseInt(dom.wAttire.value, 10),
    };

    state.weights = weights;

    // Send as 0-1 ratios to backend
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
      state.ws.send(JSON.stringify({
        type: 'update_weights',
        weights: {
          posture: weights.posture / 100,
          eye_contact: weights.eye / 100,
          body_language: weights.body / 100,
          attire: weights.attire / 100,
        },
      }));
    }

    closeModal();
  }

  // ── Candidate Workspace Logic ──────────────────────────────
  function initWorkspace() {
    const dropzone = dom.resumeDropzone;
    const fileInput = dom.resumeFileInput;

    // Trigger click on file input when dropzone is clicked
    dropzone.addEventListener('click', () => fileInput.click());

    // Drag-over styling classes
    dropzone.addEventListener('dragover', (e) => {
      e.preventDefault();
      dropzone.classList.add('dropzone--drag');
    });

    dropzone.addEventListener('dragleave', () => {
      dropzone.classList.remove('dropzone--drag');
    });

    dropzone.addEventListener('drop', (e) => {
      e.preventDefault();
      dropzone.classList.remove('dropzone--drag');
      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        handleResumeUpload(e.dataTransfer.files[0]);
      }
    });

    fileInput.addEventListener('change', (e) => {
      if (e.target.files && e.target.files.length > 0) {
        handleResumeUpload(e.target.files[0]);
      }
    });

    dom.analyzeJdBtn.addEventListener('click', handleJdAnalysis);
  }

  async function handleResumeUpload(file) {
    dom.resumeStatus.textContent = 'Uploading and parsing…';
    dom.resumeStatus.style.color = 'var(--warning)';

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch(`/api/v1/interview/upload/resume/${state.sessionId}`, {
        method: 'POST',
        body: formData
      });
      const res = await response.json();
      if (res.status === 'success') {
        dom.resumeStatus.textContent = `Resume parsed successfully: ${file.name}`;
        dom.resumeStatus.style.color = 'var(--secondary)';
        fetchMatchProfile();
      } else {
        dom.resumeStatus.textContent = `Upload failed: ${res.message || 'Unknown error'}`;
        dom.resumeStatus.style.color = 'var(--danger)';
      }
    } catch (err) {
      console.error('[Keiko] Resume upload failed:', err);
      dom.resumeStatus.textContent = 'Network error uploading resume';
      dom.resumeStatus.style.color = 'var(--danger)';
    }
  }

  async function handleJdAnalysis() {
    const jdText = dom.jdTextarea.value ? dom.jdTextarea.value.trim() : '';
    if (!jdText) {
      dom.jdStatus.textContent = 'Please paste some job description text first';
      dom.jdStatus.style.color = 'var(--danger)';
      return;
    }

    dom.jdStatus.textContent = 'Analyzing job description…';
    dom.jdStatus.style.color = 'var(--warning)';

    const formData = new FormData();
    formData.append('jd_text', jdText);

    try {
      const response = await fetch(`/api/v1/interview/upload/jd/${state.sessionId}`, {
        method: 'POST',
        body: formData
      });
      const res = await response.json();
      if (res.status === 'success') {
        dom.jdStatus.textContent = 'Job description analyzed successfully!';
        dom.jdStatus.style.color = 'var(--secondary)';
        fetchMatchProfile();
      } else {
        dom.jdStatus.textContent = `Analysis failed: ${res.message || 'Unknown error'}`;
        dom.jdStatus.style.color = 'var(--danger)';
      }
    } catch (err) {
      console.error('[Keiko] JD analysis failed:', err);
      dom.jdStatus.textContent = 'Network error analyzing JD';
      dom.jdStatus.style.color = 'var(--danger)';
    }
  }

  async function fetchMatchProfile() {
    try {
      const response = await fetch(`/api/v1/interview/profile/${state.sessionId}`);
      const data = await response.json();
      if (data && data.match_results) {
        renderMatchResults(data.match_results, data.candidate_profile, data.role_profile);
      }
    } catch (err) {
      console.error('[Keiko] Failed to fetch match profile:', err);
    }
  }

  function renderMatchResults(match, candidate, role) {
    const panel = dom.matchResultsPanel;
    panel.style.display = 'block';

    // Set Role Alignment Score Badge
    const score = Math.round(match.role_alignment_score);
    const badge = dom.alignmentScoreBadge;
    badge.textContent = `${score}%`;
    badge.className = 'alignment-score-badge';
    if (score >= 80) badge.classList.add('alignment-score-badge--high');
    else if (score >= 50) badge.classList.add('alignment-score-badge--med');
    else badge.classList.add('alignment-score-badge--low');

    // Sub-percentages
    dom.matchExpPercent.textContent = `${Math.round(match.experience_score)}%`;
    dom.matchSkillsPercent.textContent = `${Math.round(match.skill_match_score)}%`;

    // Render Strengths List
    dom.strengthsList.innerHTML = '';
    match.strengths.forEach(str => {
      const li = document.createElement('li');
      li.className = 'match-list__item match-list__item--strength';
      li.textContent = str;
      dom.strengthsList.appendChild(li);
    });

    // Render Skill Gap Tags List
    dom.gapTagsList.innerHTML = '';
    if (match.skill_gap && match.skill_gap.length > 0) {
      match.skill_gap.forEach(skill => {
        const span = document.createElement('span');
        span.className = 'tag tag--gap';
        span.textContent = skill;
        dom.gapTagsList.appendChild(span);
      });
    } else {
      dom.gapTagsList.innerHTML = '<span style="color:var(--on-surface-variant); font-size:var(--fs-xs);">No skill gaps detected.</span>';
    }

    // Render Matching and Transferable Skills Cloud
    dom.skillsTagsList.innerHTML = '';
    
    // Add matches
    match.matched_skills.forEach(item => {
      const span = document.createElement('span');
      span.className = 'tag tag--match';
      span.textContent = `${item.candidate_skill} (Match)`;
      dom.skillsTagsList.appendChild(span);
    });

    // Add transferables
    match.transferable_skills.forEach(item => {
      const span = document.createElement('span');
      span.className = 'tag tag--transferable';
      span.textContent = `${item.candidate_skill} (Transferable)`;
      dom.skillsTagsList.appendChild(span);
    });

    if (match.matched_skills.length === 0 && match.transferable_skills.length === 0) {
      dom.skillsTagsList.innerHTML = '<span style="color:var(--on-surface-variant); font-size:var(--fs-xs);">No skills aligned yet.</span>';
    }
  }

  // ── Event Listeners ────────────────────────────────────────
  function bindEvents() {
    dom.fullscreenBtn.addEventListener('click', toggleFullscreen);
    dom.settingsBtn.addEventListener('click', openModal);
    dom.modalClose.addEventListener('click', closeModal);
    dom.modalCancel.addEventListener('click', closeModal);
    dom.modalSave.addEventListener('click', saveWeights);

    // Close modal on overlay click
    dom.modalOverlay.addEventListener('click', (e) => {
      if (e.target === dom.modalOverlay) closeModal();
    });

    // Escape key
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && dom.modalOverlay.classList.contains('modal-overlay--open')) {
        closeModal();
      }
    });

    // Setup all sliders
    ['Posture', 'Eye', 'Body', 'Attire'].forEach(setupSlider);

    // Interview Events
    if (dom.startInterviewBtn) {
      dom.startInterviewBtn.addEventListener('click', () => {
        if (state.ws && state.ws.readyState === WebSocket.OPEN) {
          state.ws.send(JSON.stringify({ type: 'start_interview' }));
          dom.startInterviewBtn.style.display = 'none';
          if (dom.questionIndexLabel) dom.questionIndexLabel.style.display = 'inline';
          if (dom.questionDisplayContainer) dom.questionDisplayContainer.style.display = 'block';
          if (dom.recordingControls) dom.recordingControls.style.display = 'flex';
          if (dom.textAnswerContainer) dom.textAnswerContainer.style.display = 'flex';
        }
      });
    }

    if (dom.recordBtn) {
      dom.recordBtn.addEventListener('click', () => {
        if (!state.isRecording) {
          startAudioRecording();
          dom.recordBtn.textContent = 'Stop Recording';
          dom.recordBtn.style.background = 'var(--tertiary)';
          if (dom.recordingStatusLabel) {
            dom.recordingStatusLabel.textContent = 'Recording live audio...';
            dom.recordingStatusLabel.style.color = 'var(--secondary)';
          }
        } else {
          stopAudioRecording();
          dom.recordBtn.textContent = 'Start Recording';
          dom.recordBtn.style.background = 'var(--tertiary-container)';
          if (dom.recordingStatusLabel) {
            dom.recordingStatusLabel.textContent = 'Recording stopped';
            dom.recordingStatusLabel.style.color = 'var(--text-muted)';
          }
        }
      });
    }

    if (dom.submitAnswerBtn) {
      dom.submitAnswerBtn.addEventListener('click', () => {
        if (state.isRecording) {
          stopAudioRecording();
          dom.recordBtn.textContent = 'Start Recording';
          dom.recordBtn.style.background = 'var(--tertiary-container)';
          if (dom.recordingStatusLabel) {
            dom.recordingStatusLabel.textContent = 'Recording stopped';
            dom.recordingStatusLabel.style.color = 'var(--text-muted)';
          }
        }

        const typedAns = dom.textAnswerInput ? dom.textAnswerInput.value.trim() : '';
        if (state.ws && state.ws.readyState === WebSocket.OPEN) {
          state.ws.send(JSON.stringify({
            type: 'submit_answer',
            question: dom.questionText ? dom.questionText.textContent : '',
            answer: typedAns || ""
          }));
          if (dom.textAnswerInput) dom.textAnswerInput.value = "";
          if (dom.recordingStatusLabel) {
            dom.recordingStatusLabel.textContent = 'Submitting answer...';
            dom.recordingStatusLabel.style.color = 'var(--warning)';
          }
        }
      });
    }
  }

  let audioCtx = null;
  let audioSource = null;
  let scriptProcessor = null;

  function arrayBufferToBase64(buffer) {
    let binary = '';
    const bytes = new Uint8Array(buffer);
    const len = bytes.byteLength;
    for (let i = 0; i < len; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return window.btoa(binary);
  }

  async function startAudioRecording() {
    try {
      if (!state.stream) {
        throw new Error("Microphone stream not initialized. Please ensure camera/mic permissions are granted.");
      }
      
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      audioCtx = new AudioContextClass({ sampleRate: 16000 });
      audioSource = audioCtx.createMediaStreamSource(state.stream);
      scriptProcessor = audioCtx.createScriptProcessor(4096, 1, 1);

      scriptProcessor.onaudioprocess = (e) => {
        if (!state.connected || !state.isRecording) return;

        const input = e.inputBuffer.getChannelData(0);
        const pcm = new Int16Array(input.length);

        for (let i = 0; i < input.length; i++) {
          const s = Math.max(-1.0, Math.min(1.0, input[i]));
          pcm[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        }

        const base64Data = arrayBufferToBase64(pcm.buffer);
        if (state.ws && state.ws.readyState === WebSocket.OPEN) {
          state.ws.send(JSON.stringify({
            type: 'audio_chunk',
            data: base64Data
          }));
        }
      };

      audioSource.connect(scriptProcessor);
      scriptProcessor.connect(audioCtx.destination);

      state.isRecording = true;
      console.log('[Keiko] Audio recording started at 16000Hz mono');
    } catch (err) {
      console.error('[Keiko] Failed to start audio recording:', err);
      alert('Could not access microphone: ' + err.message);
      stopAudioRecording();
    }
  }

  function stopAudioRecording() {
    state.isRecording = false;
    
    if (scriptProcessor) {
      try {
        scriptProcessor.disconnect();
      } catch (e) {}
      scriptProcessor = null;
    }
    
    if (audioSource) {
      try {
        audioSource.disconnect();
      } catch (e) {}
      audioSource = null;
    }

    if (audioCtx) {
      try {
        audioCtx.close();
      } catch (e) {}
      audioCtx = null;
    }
    console.log('[Keiko] Audio recording stopped');
  }

  // ── Init ───────────────────────────────────────────────────
  async function loadSessionConfig() {
    try {
      const weightsRes = await fetch(`/api/v1/interview/config/weights/${state.sessionId}`);
      if (weightsRes.ok) {
        const weightsData = await weightsRes.json();
        if (weightsData && weightsData.weights) {
          console.log('[Keiko] Pre-configured weights loaded:', weightsData.weights);
        }
      }
      const profileRes = await fetch(`/api/v1/interview/profile/${state.sessionId}`);
      if (profileRes.ok) {
        const profileData = await profileRes.json();
        if (profileData && profileData.match_results) {
          console.log('[Keiko] Pre-configured profile loaded:', profileData);
          if (typeof renderMatchResults === 'function') {
            renderMatchResults(
              profileData.match_results,
              profileData.candidate_profile,
              profileData.role_profile
            );
          }
        }
      }
    } catch (err) {
      console.warn('[Keiko] Error loading pre-configured session config:', err);
    }
  }

  async function init() {
    if (dom.sessionId) dom.sessionId.textContent = state.sessionId;
    bindEvents();
    initWorkspace();
    initCamera();
    await loadSessionConfig();
    connectWS();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
