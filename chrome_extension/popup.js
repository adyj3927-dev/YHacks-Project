// popup.js — reads persistent state from chrome.storage
// Camera runs in content.js, popup just displays the live data

// ── Elements ──────────────────────────────────────────────────────────────────
const webcamFeed      = document.getElementById('webcamFeed');
const confValue       = document.getElementById('confValue');
const confBar         = document.getElementById('confBar');
const confLabel       = document.getElementById('confLabel');
const confTip         = document.getElementById('confTip');
const camError        = document.getElementById('camError');
const pomoTimer       = document.getElementById('pomoTimer');
const pomoStartBtn    = document.getElementById('pomoStartBtn');
const pomoResetBtn    = document.getElementById('pomoResetBtn');
const pomoDone        = document.getElementById('pomoDone');
const statSpikes      = document.getElementById('statSpikes');
const statFocus       = document.getElementById('statFocus');
const statCards       = document.getElementById('statCards');
const sessionDot      = document.getElementById('sessionDot');
const sessionStatus   = document.getElementById('sessionStatus');
const toggleSessionBtn= document.getElementById('toggleSessionBtn');
const openWebAppBtn   = document.getElementById('openWebAppBtn');
const syncBtn         = document.getElementById('syncBtn');

// ── State ─────────────────────────────────────────────────────────────────────
let sessionActive   = false;
let pomoMinutes     = 25;
let pomoSecondsLeft = 25 * 60;
let pomoRunning     = false;
let popupStream     = null;

// ── Load persistent state from storage on open ────────────────────────────────
chrome.storage.local.get(['session', 'pomoRunning', 'pomoStartedAt', 'pomoTotalSecs', 'timerSecs', 'confScore', 'pomoMinutes'], (res) => {
  if (res.pomoMinutes) pomoMinutes = res.pomoMinutes;

  // Restore timer display from elapsed time
  if (res.pomoRunning && res.pomoStartedAt && res.pomoTotalSecs) {
    pomoRunning = true;
    pomoStartBtn.textContent = '⏸ Pause';
    const elapsed   = Math.floor((Date.now() - res.pomoStartedAt) / 1000);
    const remaining = Math.max(0, res.pomoTotalSecs - elapsed);
    renderTimer(remaining);
  } else if (res.timerSecs !== undefined) {
    renderTimer(res.timerSecs);
  }

  if (res.session) {
    sessionActive = res.session.active || false;
    updateSessionUI();
    updateStatsUI(res.session);
  }

  if (res.confScore !== undefined) updateConfusionUI(res.confScore);

  startPopupCamera();
});

// ── Poll storage every 500ms ──────────────────────────────────────────────────
setInterval(() => {
  chrome.storage.local.get(['pomoRunning', 'pomoStartedAt', 'pomoTotalSecs', 'confScore', 'session'], (res) => {
    if (chrome.runtime.lastError) return;

    // Calculate timer from start time — accurate even if background sleeps
    if (res.pomoRunning && res.pomoStartedAt && res.pomoTotalSecs) {
      const elapsed   = Math.floor((Date.now() - res.pomoStartedAt) / 1000);
      const remaining = Math.max(0, res.pomoTotalSecs - elapsed);
      pomoSecondsLeft = remaining;
      renderTimer(remaining);
      if (remaining <= 0) {
        pomoRunning = false;
        pomoStartBtn.textContent = '▶ Start';
      }
    }

    if (res.confScore !== undefined) updateConfusionUI(res.confScore);
    if (res.session)                 updateStatsUI(res.session);
  });
}, 500);

// ── Popup camera — independent preview, does NOT affect session ───────────────
async function startPopupCamera() {
  if (popupStream) return;
  try {
    popupStream = await navigator.mediaDevices.getUserMedia({
      video: { width: 320, height: 240, facingMode: 'user' }
    });
    webcamFeed.srcObject = popupStream;
    camError.style.display = 'none';
    // Stop preview when popup closes — session in content.js stays alive
    window.addEventListener('unload', () => {
      if (popupStream) { popupStream.getTracks().forEach(t => t.stop()); popupStream = null; }
    });
  } catch(e) {
    camError.innerHTML = `Camera blocked. <a href="chrome://settings/content/camera" target="_blank" style="color:#721B06;font-weight:600">Open settings</a>`;
    camError.style.display = 'block';
  }
}

// ── Session toggle ────────────────────────────────────────────────────────────
toggleSessionBtn.addEventListener('click', async () => {
  try {
    if (sessionActive) {
      await chrome.runtime.sendMessage({ type: 'STOP_SESSION' });
      const tabs = await chrome.tabs.query({});
      tabs.forEach(tab => chrome.tabs.sendMessage(tab.id, { type: 'STOP_SESSION' }).catch(() => {}));
      sessionActive = false;
    } else {
      await chrome.runtime.sendMessage({ type: 'START_SESSION' });
      const tabs = await chrome.tabs.query({});
      tabs.forEach(tab => chrome.tabs.sendMessage(tab.id, { type: 'START_SESSION' }).catch(() => {}));
      sessionActive = true;
      startPopupCamera();
    }
    updateSessionUI();
  } catch(e) { console.error('Session toggle error:', e); }
});

// ── UI helpers ────────────────────────────────────────────────────────────────
function updateSessionUI() {
  if (sessionActive) {
    sessionDot.className         = 'dot green';
    sessionStatus.textContent    = 'Session active';
    toggleSessionBtn.textContent = 'Stop';
  } else {
    sessionDot.className         = 'dot';
    sessionStatus.textContent    = 'Session inactive';
    toggleSessionBtn.textContent = 'Start';
  }
}

function updateStatsUI(session) {
  statSpikes.textContent = session.confusionSpikes || 0;
  statFocus.textContent  = session.focusScore      || 100;
  statCards.textContent  = session.cardsDone        || 0;
  pomoDone.textContent   = `${session.pomodorosDone || 0} done today`;
}

function updateConfusionUI(score) {
  const color = score < 0.35 ? '#44422D' : score < 0.65 ? '#a16743' : '#8d4459';
  const label = score < 0.35 ? 'Calm' : score < 0.65 ? 'Uncertain' : 'Confused';
  const tip   = score < 0.35 ? 'Keep it up!' : score < 0.65 ? 'Stay focused' : 'Take a breath';
  confValue.textContent    = score.toFixed(2);
  confValue.style.color    = color;
  confBar.style.width      = `${Math.round(score*100)}%`;
  confBar.style.background = color;
  confLabel.textContent    = label;
  confTip.textContent      = tip;
  sessionDot.className     = score > 0.65 ? 'dot red' : score > 0.35 ? 'dot orange' : (sessionActive ? 'dot green' : 'dot');
}

// ── Pomodoro ──────────────────────────────────────────────────────────────────
document.querySelectorAll('.pomo-len-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.pomo-len-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    pomoMinutes     = parseInt(btn.dataset.min);
    pomoSecondsLeft = pomoMinutes * 60;
    pomoRunning     = false;
    pomoStartBtn.textContent = '▶ Start';
    chrome.storage.local.set({ pomoMinutes, pomoRunning: false });
    chrome.runtime.sendMessage({ type: 'STOP_POMODORO' });
    renderTimer(pomoSecondsLeft);
  });
});

function renderTimer(secs) {
  const m = Math.floor(secs/60).toString().padStart(2,'0');
  const s = (secs%60).toString().padStart(2,'0');
  pomoTimer.textContent = `${m}:${s}`;
}

pomoStartBtn.addEventListener('click', () => {
  if (pomoRunning) {
    pomoRunning = false;
    pomoStartBtn.textContent = '▶ Resume';
    chrome.storage.local.set({ pomoRunning: false });
    chrome.runtime.sendMessage({ type: 'STOP_POMODORO' });
  } else {
    pomoRunning = true;
    pomoStartBtn.textContent = '⏸ Pause';
    const totalSecs = pomoMinutes * 60;
    chrome.storage.local.set({
      pomoRunning: true, pomoMinutes,
      pomoStartedAt: Date.now(),
      pomoTotalSecs: totalSecs,
      timerSecs: totalSecs
    });
    chrome.runtime.sendMessage({ type: 'START_POMODORO', minutes: pomoMinutes });
  }
});

pomoResetBtn.addEventListener('click', () => {
  pomoRunning     = false;
  pomoSecondsLeft = pomoMinutes * 60;
  pomoStartBtn.textContent = '▶ Start';
  chrome.storage.local.set({ pomoRunning: false, timerSecs: pomoSecondsLeft });
  chrome.runtime.sendMessage({ type: 'STOP_POMODORO' });
  renderTimer(pomoSecondsLeft);
});

// ── Open web app ──────────────────────────────────────────────────────────────
openWebAppBtn.addEventListener('click', () => {
  chrome.tabs.create({ url: 'http://localhost:8001' });
});

// ── Sync session ──────────────────────────────────────────────────────────────
syncBtn.addEventListener('click', async () => {
  syncBtn.textContent = '⏳ Syncing...';
  syncBtn.disabled = true;
  await chrome.runtime.sendMessage({ type: 'SEND_TO_WEBAPP' });
  setTimeout(() => {
    syncBtn.textContent = '✅ Synced!';
    setTimeout(() => { syncBtn.textContent = '📤 Sync session to app'; syncBtn.disabled = false; }, 1500);
  }, 500);
});