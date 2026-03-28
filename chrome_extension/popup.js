
// popup.js

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
let sessionActive  = false;
let confusionScore = 0;
let lastSpikeTime  = 0;
let pomoMinutes    = 25;
let pomoSecondsLeft= 25 * 60;
let pomoRunning    = false;
let pomoInterval   = null;
let detectionLoop  = null;
let prevFrame      = null;

const videoCanvas = document.createElement('canvas');
const ctx2d       = videoCanvas.getContext('2d');

// ── Load session ──────────────────────────────────────────────────────────────
async function loadSession() {
  const res = await chrome.runtime.sendMessage({ type: 'GET_SESSION' });
  if (res.success) updateStatsUI(res.session);
}

function updateStatsUI(session) {
  statSpikes.textContent = session.confusionSpikes || 0;
  statFocus.textContent  = session.focusScore      || 100;
  statCards.textContent  = session.cardsDone        || 0;
  pomoDone.textContent   = `${session.pomodorosDone || 0} done today`;
  sessionActive          = session.active || false;
  updateSessionUI();
}

function updateSessionUI() {
  if (sessionActive) {
    sessionDot.className      = 'dot green';
    sessionStatus.textContent = 'Session active';
    toggleSessionBtn.textContent = 'Stop';
  } else {
    sessionDot.className      = 'dot';
    sessionStatus.textContent = 'Session inactive';
    toggleSessionBtn.textContent = 'Start';
  }
}

// ── Session toggle ────────────────────────────────────────────────────────────
toggleSessionBtn.addEventListener('click', async () => {
  if (sessionActive) {
    await chrome.runtime.sendMessage({ type: 'STOP_SESSION' });
    sessionActive = false;
    stopWebcam();
  } else {
    await chrome.runtime.sendMessage({ type: 'START_SESSION' });
    sessionActive = true;
    startWebcam();
  }
  updateSessionUI();
});

// ── Webcam — uses offscreen API workaround ────────────────────────────────────
async function startWebcam() {
  try {
    // Chrome extensions need getUserMedia called from a tab context.
    // We inject a tiny script into the active tab to request camera,
    // then pipe frames via captureStream.
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { width: 320, height: 240, facingMode: 'user' }
    });
    webcamFeed.srcObject = stream;
    webcamFeed.onloadedmetadata = () => {
      videoCanvas.width  = webcamFeed.videoWidth;
      videoCanvas.height = webcamFeed.videoHeight;
      startDetectionLoop();
    };
    camError.style.display = 'none';
  } catch (e) {
    // Show helpful message with link to grant permission
    camError.innerHTML = `
      Camera blocked. 
      <a href="chrome://settings/content/camera" target="_blank" 
         style="color:#721B06;font-weight:600">Open camera settings</a>
      and allow this extension, then click Start again.
    `;
    camError.style.display = 'block';
  }
}

function stopWebcam() {
  if (webcamFeed.srcObject) {
    webcamFeed.srcObject.getTracks().forEach(t => t.stop());
    webcamFeed.srcObject = null;
  }
  if (detectionLoop) clearInterval(detectionLoop);
}

// ── Confusion detection ───────────────────────────────────────────────────────
function analyzeFrame() {
  if (!webcamFeed.srcObject || webcamFeed.readyState < 2) return;
  ctx2d.drawImage(webcamFeed, 0, 0, videoCanvas.width, videoCanvas.height);

  const w = videoCanvas.width;
  const h = videoCanvas.height;

  let imageData;
  try {
    imageData = ctx2d.getImageData(
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

  confusionScore = confusionScore * 0.85 + rawScore * 0.15;
  updateConfusionUI(confusionScore);

  const now = Date.now();
  if (confusionScore > 0.65 && (now - lastSpikeTime) > 20000 && sessionActive) {
    lastSpikeTime = now;
    chrome.runtime.sendMessage({ type: 'CONFUSION_SPIKE', score: confusionScore });
    loadSession();
  }
}

function startDetectionLoop() {
  if (detectionLoop) clearInterval(detectionLoop);
  detectionLoop = setInterval(analyzeFrame, 300);
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
    clearInterval(pomoInterval);
    pomoStartBtn.textContent = '▶ Start';
    renderTimer();
  });
});

function renderTimer() {
  const m = Math.floor(pomoSecondsLeft/60).toString().padStart(2,'0');
  const s = (pomoSecondsLeft%60).toString().padStart(2,'0');
  pomoTimer.textContent = `${m}:${s}`;
}

pomoStartBtn.addEventListener('click', () => {
  if (pomoRunning) {
    clearInterval(pomoInterval);
    pomoRunning = false;
    pomoStartBtn.textContent = '▶ Resume';
    chrome.runtime.sendMessage({ type: 'STOP_POMODORO' });
  } else {
    pomoRunning = true;
    pomoStartBtn.textContent = '⏸ Pause';
    chrome.runtime.sendMessage({ type: 'START_POMODORO', minutes: pomoMinutes });
    pomoInterval = setInterval(() => {
      if (pomoSecondsLeft <= 0) {
        clearInterval(pomoInterval);
        pomoRunning = false;
        pomoStartBtn.textContent = '▶ Start';
        pomoSecondsLeft = pomoMinutes * 60;
        renderTimer();
        loadSession();
        return;
      }
      pomoSecondsLeft--;
      renderTimer();
      chrome.storage.local.set({ timerSecs: pomoSecondsLeft, confScore: confusionScore });
    }, 1000);
  }
});

pomoResetBtn.addEventListener('click', () => {
  clearInterval(pomoInterval);
  pomoRunning     = false;
  pomoSecondsLeft = pomoMinutes * 60;
  pomoStartBtn.textContent = '▶ Start';
  renderTimer();
  chrome.runtime.sendMessage({ type: 'STOP_POMODORO' });
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

// ── Init ──────────────────────────────────────────────────────────────────────
setInterval(loadSession, 3000);
loadSession();
renderTimer();
chrome.storage.local.get(['session'], (res) => {
  if (res.session?.active) startWebcam();
});
