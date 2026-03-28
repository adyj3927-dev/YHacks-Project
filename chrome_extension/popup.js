<<<<<<< HEAD
// popup.js — reads persistent state from chrome.storage
// Camera runs in content.js, popup just displays the live data
=======

// popup.js
>>>>>>> f7e6882e1331264977bd465251afcde8f4293f2e

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

// ── Load persistent state from storage on open ────────────────────────────────
chrome.storage.local.get(['session', 'timerSecs', 'confScore', 'pomoMinutes', 'pomoRunning'], (res) => {
  // Restore timer
  if (res.timerSecs !== undefined) {
    pomoSecondsLeft = res.timerSecs;
    renderTimer(pomoSecondsLeft);
  }
  if (res.pomoMinutes) {
    pomoMinutes = res.pomoMinutes;
  }
  if (res.pomoRunning) {
    pomoRunning = res.pomoRunning;
    pomoStartBtn.textContent = pomoRunning ? '⏸ Pause' : '▶ Start';
  }

  // Restore session
  if (res.session) {
    sessionActive = res.session.active || false;
    updateSessionUI();
    updateStatsUI(res.session);
  }

  // Restore confusion score
  if (res.confScore !== undefined) {
    updateConfusionUI(res.confScore);
  }

  // Show camera feed from content.js stream
  startPopupCamera();
});

// ── Poll storage every 500ms to stay in sync with content.js ─────────────────
setInterval(() => {
  chrome.storage.local.get(['timerSecs', 'confScore', 'session'], (res) => {
    if (res.timerSecs !== undefined) {
      pomoSecondsLeft = res.timerSecs;
      renderTimer(pomoSecondsLeft);
    }
    if (res.confScore !== undefined) {
      updateConfusionUI(res.confScore);
    }
    if (res.session) {
      updateStatsUI(res.session);
    }
  });
}, 500);

// ── Start popup's own camera feed (mirrors content.js stream) ─────────────────
async function startPopupCamera() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { width: 320, height: 240, facingMode: 'user' }
    });
    webcamFeed.srcObject = stream;
    camError.style.display = 'none';
  } catch(e) {
    camError.innerHTML = `
      Camera blocked. 
      <a href="chrome://settings/content/camera" target="_blank" 
         style="color:#721B06;font-weight:600">Open camera settings</a>
      and allow this extension, then click Start again.
    `;
    camError.style.display = 'block';
  }
}

// ── Session toggle — tells content.js to start/stop camera ───────────────────
toggleSessionBtn.addEventListener('click', async () => {
  if (sessionActive) {
    await chrome.runtime.sendMessage({ type: 'STOP_SESSION' });
    // Broadcast to all tabs
    const tabs = await chrome.tabs.query({});
    tabs.forEach(tab => chrome.tabs.sendMessage(tab.id, { type: 'STOP_SESSION' }).catch(() => {}));
    sessionActive = false;
  } else {
    await chrome.runtime.sendMessage({ type: 'START_SESSION' });
    // Broadcast to all tabs
    const tabs = await chrome.tabs.query({});
    tabs.forEach(tab => chrome.tabs.sendMessage(tab.id, { type: 'START_SESSION' }).catch(() => {}));
    sessionActive = true;
    startPopupCamera();
  }
  updateSessionUI();
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
  const color = score < 0.35 ? '#a6e3a1' : score < 0.65 ? '#fab387' : '#f38ba8';
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
    chrome.storage.local.set({ pomoRunning: true, pomoMinutes });
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
  chrome.tabs.create({ url: 'http://localhost:8501' });
});

// ── Sync session ──────────────────────────────────────────────────────────────
syncBtn.addEventListener('click', async () => {
  syncBtn.textContent = '⏳ Syncing...';
  syncBtn.disabled = true;
  await chrome.runtime.sendMessage({ type: 'SEND_TO_WEBAPP' });
  setTimeout(() => {
    syncBtn.textContent = '✅ Synced!';
    setTimeout(() => {
      syncBtn.textContent = '📤 Sync session to app';
      syncBtn.disabled = false;
    }, 1500);
  }, 500);
});
<<<<<<< HEAD
=======

// ── Init ──────────────────────────────────────────────────────────────────────
setInterval(loadSession, 3000);
loadSession();
renderTimer();
chrome.storage.local.get(['session'], (res) => {
  if (res.session?.active) startWebcam();
});
>>>>>>> f7e6882e1331264977bd465251afcde8f4293f2e
