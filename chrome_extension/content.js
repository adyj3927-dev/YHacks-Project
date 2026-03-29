// content.js — injected on every page

(function() {
  if (document.getElementById('sb-widget')) return;

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

  document.getElementById('sb-toggle').addEventListener('click', () => {
    collapsed = !collapsed;
    document.getElementById('sb-body').style.display = collapsed ? 'none' : 'block';
    document.getElementById('sb-toggle').textContent = collapsed ? '+' : '−';
    widget.style.minWidth = collapsed ? 'auto' : '180px';
  });

  let isDragging = false, startX, startY, startLeft, startTop;
  const header = document.getElementById('sb-header');
  header.addEventListener('mousedown', (e) => {
    isDragging = true;
    startX = e.clientX; startY = e.clientY;
    startLeft = parseInt(widget.style.right) || 16;
    startTop  = parseInt(widget.style.top)   || 16;
  });
  document.addEventListener('mousemove', (e) => {
    if (!isDragging) return;
    widget.style.right = `${startLeft + (startX - e.clientX)}px`;
    widget.style.top   = `${startTop  + (e.clientY - startY)}px`;
  });
  document.addEventListener('mouseup', () => { isDragging = false; });

  function renderTimer(secs) {
    const m = Math.floor(secs/60).toString().padStart(2,'0');
    const s = (secs%60).toString().padStart(2,'0');
    const el = document.getElementById('sb-timer');
    if (el) el.textContent = `${m}:${s}`;
  }

  function updateDot(score) {
    const dot  = document.getElementById('sb-conf-dot');
    const fill = document.getElementById('sb-bar-fill');
    if (!dot || !fill) return;
    const color = score < 0.35 ? '#a6e3a1' : score < 0.65 ? '#fab387' : '#f38ba8';
    dot.style.background  = color;
    fill.style.width      = `${Math.round(score*100)}%`;
    fill.style.background = color;
  }

  // ── Camera ────────────────────────────────────────────────────────────────
  const video  = document.getElementById('sb-video');
  const canvas = document.getElementById('sb-canvas');
  const ctx    = canvas.getContext('2d');
  let stream = null, detectionLoop = null, prevFrame = null;
  let confScore = 0, lastSpikeTime = 0, sessionActive = false;

  async function startCamera() {
    if (stream) return;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video:{ width:320, height:240, facingMode:'user' } });
      video.srcObject = stream;
      video.onloadedmetadata = () => {
        canvas.width = video.videoWidth; canvas.height = video.videoHeight;
        startDetectionLoop();
      };
    } catch(e) { console.log('[StudyBuddy] Camera:', e.message); }
  }

  function stopCamera() {
    if (stream) { stream.getTracks().forEach(t=>t.stop()); stream=null; }
    if (detectionLoop) clearInterval(detectionLoop);
    detectionLoop = null;
  }

  function analyzeFrame() {
    if (!stream || video.readyState < 2) return;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    let imageData;
    try {
      imageData = ctx.getImageData(
        Math.floor(canvas.width*0.25), Math.floor(canvas.height*0.15),
        Math.floor(canvas.width*0.5),  Math.floor(canvas.height*0.7)
      );
    } catch(e) { return; }

    const pixels = imageData.data;
    const n = pixels.length/4;
    let brightness=0, motionDelta=0;
    for (let i=0;i<pixels.length;i+=4) brightness+=(pixels[i]+pixels[i+1]+pixels[i+2])/3;
    brightness/=n;
    if (prevFrame && prevFrame.length===pixels.length) {
      for (let i=0;i<pixels.length;i+=4) motionDelta+=Math.abs(pixels[i]-prevFrame[i]);
      motionDelta/=n;
    }
    prevFrame = new Uint8Array(pixels);

    const raw = Math.min(1.0,
      (brightness<80?0.6:brightness<120?0.3:0) +
      (motionDelta>15?0.5:motionDelta>8?0.2:0) +
      Math.random()*0.08
    );
    confScore = confScore*0.85 + raw*0.15;

    try { chrome.storage.local.set({ confScore }); } catch(e) {}
    updateDot(confScore);

    const now = Date.now();
    if (confScore>0.65 && (now-lastSpikeTime)>20000 && sessionActive) {
      lastSpikeTime = now;
      try { chrome.runtime.sendMessage({ type:'CONFUSION_SPIKE', score:confScore }); } catch(e) {}
      widget.style.boxShadow = '0 0 0 2px #f38ba8';
      const msg = document.getElementById('sb-spike-msg');
      if (msg) { msg.style.display='block'; msg.style.cursor='pointer'; msg.onclick=()=>{ try { chrome.runtime.sendMessage({ type:'OPEN_WEBAPP' }); } catch(e) {} }; setTimeout(()=>{ widget.style.boxShadow=''; msg.style.display='none'; },5000); }
    }
  }

  function startDetectionLoop() {
    if (detectionLoop) clearInterval(detectionLoop);
    detectionLoop = setInterval(analyzeFrame, 300);
  }

  // ── Messages ──────────────────────────────────────────────────────────────
  try {
    chrome.runtime.onMessage.addListener((message) => {
      if (message.type==='START_SESSION') {
        sessionActive=true; startCamera();
        const el=document.getElementById('sb-status'); if(el) el.textContent='● Session active';
      }
      if (message.type==='STOP_SESSION') {
        sessionActive=false; stopCamera();
        const el=document.getElementById('sb-status'); if(el) el.textContent='○ Session inactive';
      }
      if (message.type==='CONFUSION_SPIKE') {
        updateDot(message.score);
        const msg=document.getElementById('sb-spike-msg');
        if(msg){ msg.style.display='block'; msg.style.cursor='pointer'; msg.onclick=()=>{ try { chrome.runtime.sendMessage({ type:'OPEN_WEBAPP' }); } catch(e) {} }; widget.style.boxShadow='0 0 0 2px #f38ba8';
          setTimeout(()=>{ widget.style.boxShadow=''; msg.style.display='none'; },5000); }
      }
      if (message.type==='PULSE_WIDGET') {
        widget.style.boxShadow='0 0 0 3px #721B06'; widget.style.transform='scale(1.05)';
        setTimeout(()=>{ widget.style.boxShadow=''; widget.style.transform=''; },1000);
      }
      if (message.type==='POMODORO_DONE') {
        const el=document.getElementById('sb-status'); if(el) el.textContent='🍅 Break time!';
        renderTimer(0);
        widget.style.boxShadow='0 0 0 2px #a6e3a1';
        setTimeout(()=>{ widget.style.boxShadow=''; },3000);
      }
    });
  } catch(e) {}

  // ── Timer — calculates from start time so it's always accurate ────────────
  function timerTick() {
    try {
      chrome.storage.local.get(['pomoRunning','pomoStartedAt','pomoTotalSecs'], (res) => {
        if (chrome.runtime.lastError || !res.pomoRunning || !res.pomoStartedAt) return;
        const elapsed   = Math.floor((Date.now() - res.pomoStartedAt) / 1000);
        const remaining = Math.max(0, (res.pomoTotalSecs||1500) - elapsed);
        renderTimer(remaining);
        if (remaining <= 0) {
          try { chrome.storage.local.set({ pomoRunning:false }); } catch(e) {}
          try { chrome.runtime.sendMessage({ type:'POMODORO_COMPLETE' }); } catch(e) {}
          const el=document.getElementById('sb-status'); if(el) el.textContent='🍅 Break time!';
          widget.style.boxShadow='0 0 0 2px #a6e3a1';
          setTimeout(()=>{ widget.style.boxShadow=''; },3000);
        }
      });
    } catch(e) { clearInterval(timerInterval); }
  }

  // ── Poll session + confusion ──────────────────────────────────────────────
  function pollState() {
    try {
      chrome.storage.local.get(['session','confScore'], (res) => {
        if (chrome.runtime.lastError) return;
        if (res.confScore !== undefined) updateDot(res.confScore);
        if (res.session) {
          sessionActive = res.session.active || false;
          const el = document.getElementById('sb-status');
          if (el && !res.session.active) el.textContent = '○ Session inactive';
          if (res.session.active && !stream) startCamera();
        }
      });
    } catch(e) { clearInterval(pollInterval); }
  }

  const timerInterval = setInterval(timerTick, 1000);
  const pollInterval  = setInterval(pollState, 1000);
  timerTick();
  pollState();

})();