// confusion_flashcards.js
// Handles flashcard generation when confusion is detected
// Injected separately — does NOT modify content.js logic

(function() {
  if (window.__sbFlashcardsLoaded) return;
  window.__sbFlashcardsLoaded = true;

  const BACKEND = 'http://localhost:8001';

  // ── Extract visible text from page ────────────────────────────────────────
  function extractPageText() {
    try {
      const clone = document.body.cloneNode(true);
      ['script','style','noscript','nav','footer','#sb-widget','#sb-fc-overlay']
        .forEach(sel => clone.querySelectorAll(sel).forEach(el => el.remove()));
      return (clone.innerText || '').replace(/\s+/g,' ').trim().slice(0, 5000);
    } catch(e) { return ''; }
  }

  // ── Generate flashcards from backend ─────────────────────────────────────
  async function generateFlashcards() {
    const text = extractPageText();
    if (!text || text.length < 100) return;

    let lang = 'English';
    try {
      const stored = await new Promise(r => chrome.storage.local.get(['selectedLanguage'], r));
      lang = stored.selectedLanguage || 'English';
    } catch(e) {}

    // Show loading indicator
    showLoadingOverlay(lang);

    try {
      const res = await fetch(`${BACKEND}/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, language: lang, confusion_score: 0.75 })
      });
      if (!res.ok) { hideLoadingOverlay(); return; }
      const data = await res.json();
      if (data.flashcards && data.flashcards.length) {
        showFlashcardOverlay(data.flashcards, data.questions || [], data.summary || '', lang);
      } else {
        hideLoadingOverlay();
      }
    } catch(e) {
      hideLoadingOverlay();
    }
  }

  // ── Loading overlay ───────────────────────────────────────────────────────
  function showLoadingOverlay(lang) {
    const old = document.getElementById('sb-fc-overlay');
    if (old) old.remove();
    const el = document.createElement('div');
    el.id = 'sb-fc-overlay';
    el.style.cssText = overlayBaseStyle();
    el.innerHTML = `
      <div style="text-align:center;padding:20px">
        <div style="font-size:28px;margin-bottom:12px">🧠</div>
        <div style="font-size:14px;color:#443223;margin-bottom:6px">Confusion detected!</div>
        <div style="font-size:12px;color:#888676">Generating flashcards in ${lang}…</div>
        <div style="margin-top:16px;width:30px;height:30px;border:2px solid #313244;border-top-color:#cba6f7;border-radius:50%;animation:sb-spin .8s linear infinite;margin:16px auto 0"></div>
      </div>
      <style>@keyframes sb-spin{to{transform:rotate(360deg)}}</style>
    `;
    document.body.appendChild(el);
  }

  function hideLoadingOverlay() {
    const el = document.getElementById('sb-fc-overlay');
    if (el) el.remove();
  }

  // ── Flashcard overlay ─────────────────────────────────────────────────────
  function showFlashcardOverlay(cards, questions, summary, lang) {
    hideLoadingOverlay();

    const isRTL  = ['Arabic','Urdu'].includes(lang);
    let fcIdx    = 0;
    let mcqIdx   = 0;
    let flipped  = false;
    let activeTab = 'cards';

    const overlay = document.createElement('div');
    overlay.id = 'sb-fc-overlay';
    overlay.style.cssText = overlayBaseStyle() + (isRTL ? 'direction:rtl;' : '');
    document.body.appendChild(overlay);

    function render() {
      const card = cards[fcIdx];
      const q    = questions[mcqIdx];

      overlay.innerHTML = `
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
          <div style="font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:#cba6f7">🧠 Confusion · ${lang}</div>
          <button id="sb-close" style="background:none;border:none;color:#888676;cursor:pointer;font-size:18px;line-height:1;padding:2px 6px">✕</button>
        </div>
        ${summary ? `<div style="font-size:12px;color:#888676;font-style:italic;margin-bottom:12px;line-height:1.5;padding:8px;background:#F7F5F3;border-radius:8px">${summary}</div>` : ''}

        <div style="display:flex;gap:6px;margin-bottom:12px">
          <button id="sb-tab-cards" style="${tabStyle(activeTab==='cards')}">Flashcards</button>
          ${questions.length ? `<button id="sb-tab-quiz" style="${tabStyle(activeTab==='quiz')}">Quiz</button>` : ''}
        </div>

        ${activeTab === 'cards' ? `
          <div style="font-size:11px;color:#888676;text-align:center;margin-bottom:6px">Tap to flip · Card ${fcIdx+1} of ${cards.length}</div>
          <div id="sb-card" style="background:#EDE3D6;border:1px solid #45475a;border-radius:12px;padding:18px;min-height:90px;cursor:pointer;margin-bottom:12px;transition:background .2s">
            <div style="font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:#888676;margin-bottom:8px" id="sb-card-lbl">${flipped?'Answer':'Question'}</div>
            <div style="font-size:15px;color:#443223;line-height:1.5" id="sb-card-txt">${flipped ? card.back + (card.hint?` <span style="font-size:12px;color:#c9a96e;display:block;margin-top:8px">💡 ${card.hint}</span>`:'') : card.front}</div>
          </div>
          <div style="display:flex;gap:8px">
            <button id="sb-prev" style="${navBtnStyle()}">← Prev</button>
            <button id="sb-got"  style="${navBtnStyle('green')}">✅ Got it!</button>
            <button id="sb-next" style="${navBtnStyle()}">Next →</button>
          </div>
        ` : `
          <div style="font-size:11px;color:#888676;margin-bottom:10px">Question ${mcqIdx+1} of ${questions.length}</div>
          <div style="font-size:14px;color:#443223;margin-bottom:12px;line-height:1.5">${q.question}</div>
          <div id="sb-opts">
            ${q.options.map((o,i)=>`<div class="sb-opt" data-i="${i}" style="${optStyle()}">${'ABCD'[i]}. ${o}</div>`).join('')}
          </div>
          <div id="sb-exp" style="display:none;font-size:12px;color:#888676;margin-top:10px;padding:8px;background:#F7F5F3;border-radius:8px;line-height:1.5"></div>
          ${mcqIdx < questions.length-1 ? `<button id="sb-next-q" style="${navBtnStyle()};width:100%;margin-top:10px;display:none">Next question →</button>` : ''}
        `}
      `;

      // Close
      document.getElementById('sb-close').onclick = () => overlay.remove();

      // Tabs
      document.getElementById('sb-tab-cards')?.addEventListener('click', () => { activeTab='cards'; flipped=false; render(); });
      document.getElementById('sb-tab-quiz')?.addEventListener('click',  () => { activeTab='quiz';  render(); });

      if (activeTab === 'cards') {
        // Flip
        document.getElementById('sb-card').onclick = () => { flipped=!flipped; render(); };
        // Nav
        document.getElementById('sb-prev').onclick = () => { fcIdx=Math.max(0,fcIdx-1); flipped=false; render(); };
        document.getElementById('sb-next').onclick = () => { fcIdx=Math.min(cards.length-1,fcIdx+1); flipped=false; render(); };
        document.getElementById('sb-got').onclick  = () => {
          try { chrome.runtime.sendMessage({ type:'CARD_DONE' }); } catch(e) {}
          if (fcIdx < cards.length-1) { fcIdx++; flipped=false; render(); }
          else overlay.remove();
        };
      } else {
        // MCQ
        let answered = false;
        document.querySelectorAll('.sb-opt').forEach(el => {
          el.addEventListener('click', () => {
            if (answered) return;
            answered = true;
            const chosen = parseInt(el.dataset.i);
            document.querySelectorAll('.sb-opt').forEach((o,i) => {
              if (i===q.correct_index) o.style.cssText = optStyle('correct');
              else if (i===chosen)     o.style.cssText = optStyle('wrong');
            });
            document.getElementById('sb-exp').textContent = q.explanation;
            document.getElementById('sb-exp').style.display = 'block';
            const nextBtn = document.getElementById('sb-next-q');
            if (nextBtn) nextBtn.style.display = 'block';
          });
        });
        document.getElementById('sb-next-q')?.addEventListener('click', () => { mcqIdx++; render(); });
      }
    }

    render();
    // Auto-dismiss after 90 seconds
    setTimeout(() => { if (overlay.parentNode) overlay.remove(); }, 90000);
  }

  // ── Style helpers ─────────────────────────────────────────────────────────
  function overlayBaseStyle() {
    return `position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:#FFF9F3;border:1.5px solid rgba(114,88,62,0.3);border-radius:16px;padding:22px 26px;width:380px;max-width:90vw;z-index:2147483646;box-shadow:0 20px 60px rgba(0,0,0,0.6);font-family:'DM Sans',sans-serif;`;
  }
  function tabStyle(active) {
    return `flex:1;padding:6px 14px;border-radius:20px;border:${active?'1px solid #cba6f7':'1px solid #313244'};background:${active?'rgba(203,166,247,.15)':'none'};color:${active?'#cba6f7':'#6c7086'};font-size:12px;cursor:pointer;font-family:'DM Sans',sans-serif;`;
  }
  function navBtnStyle(type='') {
    const styles = {
      '':      'flex:1;padding:8px;border-radius:8px;border:1px solid #313244;background:#F7F5F3;color:#443223;font-size:12px;cursor:pointer;font-family:\'DM Sans\',sans-serif',
      'green': 'flex:1;padding:8px;border-radius:8px;border:1px solid rgba(111,207,151,.3);background:rgba(111,207,151,.1);color:#6fcf97;font-size:12px;cursor:pointer;font-family:\'DM Sans\',sans-serif',
    };
    return styles[type] || styles[''];
  }
  function optStyle(state='') {
    const base = 'display:flex;align-items:flex-start;gap:8px;padding:9px 12px;border-radius:8px;font-size:13px;cursor:pointer;margin-bottom:5px;line-height:1.4;font-family:\'DM Sans\',sans-serif;';
    if (state==='correct') return base+'border:1px solid rgba(111,207,151,.3);background:rgba(111,207,151,.08);color:#6fcf97;';
    if (state==='wrong')   return base+'border:1px solid rgba(235,87,87,.3);background:rgba(235,87,87,.08);color:#eb5757;';
    return base+'border:1px solid #313244;background:#F7F5F3;color:#443223;';
  }

  // ── Listen for confusion spike message ────────────────────────────────────
  try {
    chrome.runtime.onMessage.addListener((message) => {
      if (message.type === 'CONFUSION_SPIKE') {
        generateFlashcards();
      }
    });
  } catch(e) {}

  // ── Also watch storage for confusion spikes (backup trigger) ──────────────
  let lastSpike = 0;
  setInterval(() => {
    try {
      chrome.storage.local.get(['confScore','session'], (res) => {
        if (chrome.runtime.lastError) return;
        if (res.confScore > 0.65 && res.session?.active) {
          const now = Date.now();
          if (now - lastSpike > 20000) {
            lastSpike = now;
            generateFlashcards();
          }
        }
      });
    } catch(e) {}
  }, 2000);

})();