// content.js — injected on every page
// Shows floating pomodoro timer + confusion indicator

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
  `;
  document.body.appendChild(widget);

  let collapsed  = false;
  let timerSecs  = 25 * 60;
  let timerRunning = false;

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
    const dot = document.getElementById('sb-conf-dot');
    const fill = document.getElementById('sb-bar-fill');
    const color = score < 0.35 ? '#a6e3a1' : score < 0.65 ? '#fab387' : '#f38ba8';
    dot.style.background   = color;
    fill.style.width        = `${Math.round(score * 100)}%`;
    fill.style.background   = color;
  }

  // ── Listen for messages from background ────────────────────────────────────
  chrome.runtime.onMessage.addListener((message) => {
    if (message.type === 'CONFUSION_SPIKE') {
      updateDot(message.score);
      const msg = document.getElementById('sb-spike-msg');
      msg.style.display = 'block';
      // Flash widget
      widget.style.boxShadow = '0 0 0 2px #f38ba8';
      setTimeout(() => {
        widget.style.boxShadow = '';
        msg.style.display = 'none';
      }, 5000);
    }

    if (message.type === 'POMODORO_DONE') {
      document.getElementById('sb-status').textContent = '🍅 Break time!';
      document.getElementById('sb-timer').textContent  = '00:00';
      widget.style.boxShadow = '0 0 0 2px #a6e3a1';
      setTimeout(() => { widget.style.boxShadow = ''; }, 3000);
    }

    if (message.type === 'TIMER_TICK') {
      renderTimer(message.secs);
      updateDot(message.confScore || 0);
      document.getElementById('sb-status').textContent =
        message.sessionActive ? '● Session active' : '○ Session inactive';
    }
  });

  // ── Poll storage for timer + session state ─────────────────────────────────
  function pollState() {
    chrome.storage.local.get(['session', 'timerSecs', 'confScore'], (res) => {
      if (res.timerSecs !== undefined) renderTimer(res.timerSecs);
      if (res.confScore  !== undefined) updateDot(res.confScore);
      if (res.session) {
        document.getElementById('sb-status').textContent =
          res.session.active ? '● Session active' : '○ Session inactive';
      }
    });
  }
  setInterval(pollState, 1000);
  pollState();
})();