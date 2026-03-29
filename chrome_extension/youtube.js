// youtube.js — YouTube translation, injected on watch pages only

(function() {
  if (window.__sbYouTubeLoaded) return;
  window.__sbYouTubeLoaded = true;

  const BACKEND = 'http://localhost:8001';
  let transcript=[], translated=[], lastVideoId=null, subtitleEl=null, subtitleLoop=null;

  function getVideoId() {
    try { return new URL(location.href).searchParams.get('v'); } catch(e) { return null; }
  }

  function setWidgetStatus(msg) {
    const el = document.getElementById('sb-status');
    if (el) el.textContent = msg;
  }

  // ── Fetch transcript via background script (avoids CORS) ──────────────────
  function fetchTranscriptViaBackground(videoId) {
    return new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage({ type:'FETCH_TRANSCRIPT', videoId }, (res) => {
          if (chrome.runtime.lastError || !res || !res.success) { resolve(null); return; }
          resolve(res.transcript);
        });
      } catch(e) { resolve(null); }
    });
  }

  // ── Translate via backend ─────────────────────────────────────────────────
  async function translateLines(lines, language) {
    if (language==='English') return lines;
    const chunks=[];
    for (let i=0;i<lines.length;i+=25) chunks.push(lines.slice(i,i+25));
    const results = await Promise.all(chunks.map(async chunk => {
      try {
        const res = await fetch(`${BACKEND}/translate-text`, {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({ text: chunk.map(l=>l.text).join('\n'), language })
        });
        if (!res.ok) return chunk;
        const data = await res.json();
        const tLines = data.translated.split('\n');
        return chunk.map((l,i)=>({ ...l, text: tLines[i]||l.text }));
      } catch(e) { return chunk; }
    }));
    return results.flat();
  }

  // ── Subtitle overlay ──────────────────────────────────────────────────────
  function createOverlay() {
    const old = document.getElementById('sb-subtitles');
    if (old) old.remove();
    subtitleEl = document.createElement('div');
    subtitleEl.id = 'sb-subtitles';
    subtitleEl.style.cssText = `
      position:absolute;bottom:70px;left:50%;transform:translateX(-50%);
      background:rgba(0,0,0,0.85);color:#fff;font-size:17px;
      font-family:sans-serif;padding:7px 20px;border-radius:6px;
      max-width:80%;text-align:center;z-index:9999;
      pointer-events:none;line-height:1.5;display:none;
    `;
    const player = document.querySelector('#movie_player') ||
                   document.querySelector('.html5-video-container') ||
                   document.querySelector('video')?.parentElement;
    if (player) {
      if (getComputedStyle(player).position==='static') player.style.position='relative';
      player.appendChild(subtitleEl);
    }
  }

  function startSync(video) {
    if (subtitleLoop) clearInterval(subtitleLoop);
    subtitleLoop = setInterval(() => {
      if (!subtitleEl || !translated.length) return;
      const t    = video.currentTime;
      const line = translated.find(l => t>=l.start && t<=l.start+l.dur);
      if (line) { subtitleEl.textContent=line.text; subtitleEl.style.display='block'; }
      else        subtitleEl.style.display='none';
    }, 150);
  }

  // ── Show notes in widget ──────────────────────────────────────────────────
  function showNotes(summary, notes, lang) {
    let el = document.getElementById('sb-yt-notes');
    if (!el) {
      el = document.createElement('div');
      el.id = 'sb-yt-notes';
      el.style.cssText=`margin-top:8px;background:rgba(201,169,110,0.1);border:1px solid rgba(201,169,110,0.3);border-radius:6px;padding:8px;font-size:11px;color:#e8e6f0;line-height:1.5;max-height:130px;overflow-y:auto;`;
      const body = document.getElementById('sb-body');
      if (body) body.appendChild(el);
    }
    el.innerHTML=`<div style="font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:#c9a96e;margin-bottom:5px">📺 ${lang} Notes</div>
<div style="margin-bottom:6px;color:#a6adc8;font-style:italic">${summary}</div>
${notes.map(n=>`<div style="padding:2px 0;border-bottom:1px solid rgba(255,255,255,0.05)">• ${n}</div>`).join('')}`;
  }

  // ── Main init ─────────────────────────────────────────────────────────────
  async function init() {
    const videoId = getVideoId();
    if (!videoId) return;

    chrome.storage.local.get(['selectedLanguage'], async (res) => {
      const lang = res.selectedLanguage || 'English';
      setWidgetStatus('📺 Loading transcript…');

      transcript = await fetchTranscriptViaBackground(videoId);
      if (!transcript || !transcript.length) {
        setWidgetStatus('📺 No captions found');
        return;
      }

      setWidgetStatus(`📺 Translating to ${lang}…`);
      translated = await translateLines(transcript, lang);

      createOverlay();

      // Wait for video
      const waitVideo = (cb) => {
        const iv = setInterval(()=>{ const v=document.querySelector('video'); if(v){clearInterval(iv);cb(v);} },500);
      };
      waitVideo(v => { startSync(v); setWidgetStatus(`📺 ${lang} subtitles ON`); });

      // Notes
      try {
        const fullText = transcript.map(l=>l.text).join(' ');
        const noteRes  = await fetch(`${BACKEND}/generate`, {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({ text:fullText.slice(0,4000), language:lang, confusion_score:0.3 })
        });
        if (noteRes.ok) {
          const data = await noteRes.json();
          const keyNotes = (data.flashcards||[]).slice(0,3).map(f=>`${f.front}: ${f.back}`);
          showNotes(data.summary||'', keyNotes, lang);
        }
      } catch(e) {}
    });
  }

  // ── Navigation watcher ────────────────────────────────────────────────────
  function checkNav() {
    const id = getVideoId();
    if (id && id!==lastVideoId) {
      lastVideoId = id;
      if (subtitleLoop) clearInterval(subtitleLoop);
      translated=[];
      ['sb-subtitles','sb-yt-notes'].forEach(eid=>{ const el=document.getElementById(eid); if(el) el.remove(); });
      subtitleEl=null;
      setTimeout(init, 2500);
    }
  }

  new MutationObserver(checkNav).observe(document.documentElement, { childList:true, subtree:true });
  setInterval(checkNav, 2000);

  lastVideoId = getVideoId();
  if (lastVideoId) setTimeout(init, 2500);
})();