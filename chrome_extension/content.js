// content.js — injected on every page
// Shows floating widget + runs persistent camera confusion detection

(function() {
  if (document.getElementById('sb-widget')) return; // already injected

  // ── Create widget HTML ──────────────────────────────────────────────────────
  const widget = document.createElement('div');
  widget.id = 'sb-widget';
  widget.innerHTML = `
    <div id="sb-header">
      <span id="sb-logo">📖 StudyBuddy</span>
      <button id="sb-toggle">−</button>
    </div>
    <div id="sb-body">
      <div id="sb-timer-row">
        <span id="sb-timer">25:00</span>
        <div id="sb-conf-dot" title="Confusion level"></div>
      </div>
      <div id="sb-bar-bg"><div id="sb-bar-fill"></div></div>
      <div id="sb-status">Session inactive</div>
      <div id="sb-spike-msg" style="display:none">🧠 Confusion detected! Open the app for flashcards.</div>
    </div>
    <video id="sb-video" autoplay muted playsinline style="display:none;width:0;height:0;position:absolute;"></video>
    <canvas id="sb-canvas" style="display:none;position:absolute;"></canvas>
  `;
  document.body.appendChild(widget);

  let collapsed = false;

  // ── Collapse/expand ─────────────────────────────────────────────────────────
  document.getElementById('sb-toggle').addEventListener('click', () => {
    collapsed = !collapsed;
    document.getElementById('sb-body').style.display = collapsed ? 'none' : 'block';
    document.getElementById('sb-toggle').textContent = collapsed ? '+' : '−';
    widget.style.minWidth = collapsed ? 'auto' : '180px';
  });

  // ── Draggable ───────────────────────────────────────────────────────────────
  let isDragging = false, startX, startY, startLeft, startTop;
  const header = document.getElementById('sb-header');
  header.addEventListener('mousedown', (e) => {
    isDragging = true;
    startX    = e.clientX;
    startY    = e.clientY;
    startLeft = parseInt(widget.style.right) || 16;
    startTop  = parseInt(widget.style.top)   || 16;
  });
  document.addEventListener('mousemove', (e) => {
    if (!isDragging) return;
    const dx = startX - e.clientX;
    const dy = e.clientY - startY;
    widget.style.right = `${startLeft + dx}px`;
    widget.style.top   = `${startTop  + dy}px`;
  });
  document.addEventListener('mouseup', () => { isDragging = false; });

  // ── Render timer ────────────────────────────────────────────────────────────
  function renderTimer(secs) {
    const m = Math.floor(secs / 60).toString().padStart(2, '0');
    const s = (secs % 60).toString().padStart(2, '0');
    document.getElementById('sb-timer').textContent = `${m}:${s}`;
  }

  // ── Update confusion dot ────────────────────────────────────────────────────
  function updateDot(score) {
    const dot  = document.getElementById('sb-conf-dot');
    const fill = document.getElementById('sb-bar-fill');
    const color = score < 0.35 ? '#a6e3a1' : score < 0.65 ? '#fab387' : '#f38ba8';
    dot.style.background  = color;
    fill.style.width      = `${Math.round(score * 100)}%`;
    fill.style.background = color;
  }

  // ── Camera + confusion detection ────────────────────────────────────────────
  const video   = document.getElementById('sb-video');
  const canvas  = document.getElementById('sb-canvas');
  const ctx     = canvas.getContext('2d');
  let stream    = null;
  let detectionLoop = null;
  let prevFrame = null;
  let confScore = 0;
  let lastSpikeTime = 0;
  let sessionActive = false;

  async function startCamera() {
    if (stream) return; // already running
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 320, height: 240, facingMode: 'user' }
      });
      video.srcObject = stream;
      video.onloadedmetadata = () => {
        canvas.width  = video.videoWidth;
        canvas.height = video.videoHeight;
        startDetectionLoop();
      };
    } catch(e) {
      console.log('[StudyBuddy] Camera not available in content script:', e.message);
    }
  }

  function stopCamera() {
    if (stream) {
      stream.getTracks().forEach(t => t.stop());
      stream = null;
    }
    if (detectionLoop) clearInterval(detectionLoop);
    detectionLoop = null;
  }

  function analyzeFrame() {
    if (!stream || video.readyState < 2) return;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    const w = canvas.width;
    const h = canvas.height;
    let imageData;
    try {
      imageData = ctx.getImageData(
        Math.floor(w*0.25), Math.floor(h*0.15),
        Math.floor(w*0.5),  Math.floor(h*0.7)
      );
    } catch(e) { return; }

    const pixels = imageData.data;
    const n = pixels.length / 4;
    let brightness = 0, motionDelta = 0;

    for (let i = 0; i < pixels.length; i += 4) {
      brightness += (pixels[i] + pixels[i+1] + pixels[i+2]) / 3;
    }
    brightness /= n;

    if (prevFrame && prevFrame.length === pixels.length) {
      for (let i = 0; i < pixels.length; i += 4) {
        motionDelta += Math.abs(pixels[i] - prevFrame[i]);
      }
      motionDelta /= n;
    }
    prevFrame = new Uint8Array(pixels);

    const brightScore = brightness < 80 ? 0.6 : brightness < 120 ? 0.3 : 0.0;
    const motionScore = motionDelta > 15 ? 0.5 : motionDelta > 8 ? 0.2 : 0.0;
    const rawScore    = Math.min(1.0, brightScore + motionScore + Math.random() * 0.08);

    confScore = confScore * 0.85 + rawScore * 0.15;

    // Write score to storage so popup can read it
    chrome.storage.local.set({ confScore });
    updateDot(confScore);

    // Spike detection
    const now = Date.now();
    if (confScore > 0.65 && (now - lastSpikeTime) > 20000 && sessionActive) {
      lastSpikeTime = now;
      chrome.runtime.sendMessage({ type: 'CONFUSION_SPIKE', score: confScore });
      // Flash widget
      widget.style.boxShadow = '0 0 0 2px #f38ba8';
      const msg = document.getElementById('sb-spike-msg');
      msg.style.display = 'block';
      setTimeout(() => {
        widget.style.boxShadow = '';
        msg.style.display = 'none';
      }, 5000);
    }
  }

  function startDetectionLoop() {
    if (detectionLoop) clearInterval(detectionLoop);
    detectionLoop = setInterval(analyzeFrame, 300);
  }

  // ── Listen for messages from background/popup ──────────────────────────────
  chrome.runtime.onMessage.addListener((message) => {
    if (message.type === 'START_SESSION') {
      sessionActive = true;
      startCamera();
      document.getElementById('sb-status').textContent = '● Session active';
    }

    if (message.type === 'STOP_SESSION') {
      sessionActive = false;
      stopCamera();
      document.getElementById('sb-status').textContent = '○ Session inactive';
    }

    if (message.type === 'CONFUSION_SPIKE') {
      updateDot(message.score);
      const msg = document.getElementById('sb-spike-msg');
      msg.style.display = 'block';
      widget.style.boxShadow = '0 0 0 2px #f38ba8';
      setTimeout(() => {
        widget.style.boxShadow = '';
        msg.style.display = 'none';
      }, 5000);
    }

    if (message.type === 'PULSE_WIDGET') {
      // Flash the widget so user knows it's here
      widget.style.boxShadow = '0 0 0 3px #721B06';
      widget.style.transform = 'scale(1.05)';
      setTimeout(() => {
        widget.style.boxShadow = '';
        widget.style.transform = '';
      }, 1000);
    }

    if (message.type === 'POMODORO_DONE') {
      document.getElementById('sb-status').textContent = '🍅 Break time!';
      document.getElementById('sb-timer').textContent  = '00:00';
      widget.style.boxShadow = '0 0 0 2px #a6e3a1';
      setTimeout(() => { widget.style.boxShadow = ''; }, 3000);
    }
  });

  // ── Poll storage for timer + session state ─────────────────────────────────
  function pollState() {
    chrome.storage.local.get(['session', 'timerSecs', 'confScore'], (res) => {
      if (res.timerSecs !== undefined) renderTimer(res.timerSecs);
      if (res.confScore  !== undefined) updateDot(res.confScore);
      if (res.session) {
        sessionActive = res.session.active || false;
        document.getElementById('sb-status').textContent =
          res.session.active ? '● Session active' : '○ Session inactive';
        // Auto-start camera if session was active
        if (res.session.active && !stream) startCamera();
      }
    });
  }
  setInterval(pollState, 1000);
  pollState();
})();
