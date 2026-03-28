"""
StudyBuddy — Main Streamlit App (with live screen reading)
Run with: streamlit run app.py
"""

import streamlit as st
import time
import os
from pathlib import Path

from text_extractor import TextExtractor, TextContext
from flashcard_generator import GeminiFlashcardGenerator, StudySet
from screen_capture import ContextManager, ScreenContext

try:
    from confusion_detector import ConfusionDetector
    WEBCAM_AVAILABLE = True
except Exception:
    WEBCAM_AVAILABLE = False

st.set_page_config(page_title="StudyBuddy", page_icon="🧠", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@400;500;600&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
h1, h2, h3 { font-family: 'DM Serif Display', serif; }
.screen-panel { background:#1e1e2e; border:1px solid #313244; border-radius:14px; padding:18px 22px; margin:10px 0; }
.screen-app   { font-size:11px; color:#6c7086; text-transform:uppercase; letter-spacing:.08em; margin-bottom:4px; }
.screen-topic { font-family:'DM Serif Display',serif; font-size:20px; color:#cdd6f4; margin-bottom:6px; }
.screen-kw    { display:inline-block; background:#313244; color:#89b4fa; border-radius:6px; padding:2px 8px; font-size:12px; margin:2px 3px 2px 0; }
.conf-bar-wrap { background:#1e1e2e; border-radius:8px; padding:12px 16px; margin:8px 0; }
.conf-label { font-size:12px; color:#a6adc8; margin-bottom:6px; }
.conf-bar-bg { background:#313244; border-radius:4px; height:10px; width:100%; }
.conf-bar-fill { border-radius:4px; height:10px; transition:width 0.4s ease; }
.flashcard { background:linear-gradient(135deg,#1e1e2e 0%,#2a2a3e 100%); border:1px solid #45475a; border-radius:16px; padding:28px 32px; margin:12px 0; }
.flashcard-term { font-family:'DM Serif Display',serif; font-size:20px; color:#cdd6f4; margin-bottom:12px; }
.flashcard-def  { font-size:15px; color:#a6adc8; line-height:1.6; }
.flashcard-hint { font-size:13px; color:#6c7086; margin-top:10px; font-style:italic; }
.mcq-box { background:#181825; border:1px solid #313244; border-radius:12px; padding:20px 24px; margin:8px 0; }
.mcq-q   { font-size:15px; color:#cdd6f4; font-weight:500; margin-bottom:12px; }
.focus-alert { background:#1e1e2e; border:2px solid #f38ba8; border-radius:16px; padding:24px 28px; text-align:center; }
.focus-alert h3 { color:#f38ba8; font-family:'DM Serif Display',serif; }
.focus-alert p  { color:#a6adc8; }
.score-badge { display:inline-block; padding:4px 12px; border-radius:20px; font-size:13px; font-weight:600; }
.score-low    { background:#a6e3a1; color:#1e1e2e; }
.score-medium { background:#fab387; color:#1e1e2e; }
.score-high   { background:#f38ba8; color:#1e1e2e; }
.stat-card { background:#1e1e2e; border:1px solid #313244; border-radius:10px; padding:14px 16px; margin:6px 0; text-align:center; }
.stat-value { font-size:28px; font-family:'DM Serif Display',serif; color:#cdd6f4; }
.stat-label { font-size:12px; color:#6c7086; margin-top:2px; }
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────
def _init():
    defaults = {
        "confusion_score":    0.0,
        "study_set":          None,
        "show_flashcards":    False,
        "show_focus_alert":   False,
        "session_start":      time.time(),
        "cards_completed":    0,
        "confusion_spikes":   0,
        "focus_alerts":       0,
        "current_card_idx":   0,
        "current_q_idx":      0,
        "answer_submitted":   False,
        "selected_option":    None,
        "api_key":            os.environ.get("GEMINI_API_KEY", ""),
        "detector":           None,
        "ctx_manager":        None,
        "last_spike_t":       0,
        "screen_ctx":         None,
        "screen_status":      "idle",
        "manual_text_ctx":    None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init()

# ── Start screen reader once ──────────────────────────────────────────────────
if st.session_state.ctx_manager is None:
    mgr = ContextManager()
    started = mgr.start()
    st.session_state.ctx_manager = mgr
    st.session_state.screen_status = "capturing" if started else "error"

ctx_mgr: ContextManager = st.session_state.ctx_manager

# ── Helpers ───────────────────────────────────────────────────────────────────
def confusion_color(s): return "#a6e3a1" if s < 0.4 else "#fab387" if s < 0.7 else "#f38ba8"
def confusion_label(s): return "low" if s < 0.4 else "medium" if s < 0.7 else "high"
def session_elapsed():
    s = int(time.time() - st.session_state.session_start)
    return f"{s//60:02d}:{s%60:02d}"

def trigger_flashcards():
    api_key = st.session_state.api_key
    if not api_key:
        st.warning("Enter your Gemini API key in the sidebar.")
        return

    # Force an immediate screen grab at the moment of confusion
    live_ctx = ctx_mgr.capture_now()
    ctx = live_ctx if (live_ctx and not live_ctx.is_empty()) else st.session_state.manual_text_ctx

    if ctx is None:
        st.warning("No content detected. Open a study material or paste text in the sidebar.")
        return

    class _Adapter:
        def __init__(self, c):
            self.snippet        = c.snippet if hasattr(c, 'snippet') else c.text[:2000]
            self.topic_keywords = c.topic_keywords

    with st.spinner("Reading your screen and generating flashcards…"):
        try:
            gen = GeminiFlashcardGenerator(api_key=api_key)
            st.session_state.study_set = gen.generate(
                _Adapter(ctx),
                confusion_score=st.session_state.confusion_score,
                num_flashcards=3,
                num_questions=2,
            )
            st.session_state.show_flashcards   = True
            st.session_state.confusion_spikes += 1
            st.session_state.current_card_idx  = 0
            st.session_state.current_q_idx     = 0
            st.session_state.answer_submitted  = False
            st.session_state.selected_option   = None
            st.session_state.last_spike_t      = time.time()
            st.session_state.screen_ctx        = live_ctx
        except Exception as e:
            st.error(f"Gemini error: {e}")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🧠 StudyBuddy")

    status = st.session_state.screen_status
    status_color = {"capturing": "#a6e3a1", "error": "#f38ba8", "idle": "#6c7086"}[status]
    status_text  = {"capturing": "● Screen reading active", "error": "⚠ Screen read unavailable", "idle": "○ Idle"}[status]
    st.markdown(f'<span style="font-size:12px;color:{status_color}">{status_text}</span>', unsafe_allow_html=True)
    st.markdown("---")

    st.session_state.api_key = st.text_input(
        "Gemini API Key", value=st.session_state.api_key,
        type="password", help="https://aistudio.google.com/app/apikey"
    )

    st.markdown("---")
    st.markdown("### Manual content (fallback)")
    st.caption("Used when screen OCR isn't available or you want to override")
    manual_mode = st.radio("", ["Demo lesson", "Upload PDF", "Paste text"], label_visibility="collapsed")
    ext = TextExtractor()

    if manual_mode == "Demo lesson":
        demo_topic = st.selectbox("Topic", ["photosynthesis", "newton_laws"])
        if st.button("Load demo lesson", use_container_width=True):
            st.session_state.manual_text_ctx = ext.demo_text(demo_topic)
            st.success("Demo lesson loaded!")
    elif manual_mode == "Upload PDF":
        uploaded = st.file_uploader("Upload PDF", type=["pdf"])
        if uploaded and st.button("Extract text", use_container_width=True):
            tmp = Path("/tmp/studybuddy_upload.pdf")
            tmp.write_bytes(uploaded.read())
            st.session_state.manual_text_ctx = ext.from_pdf(str(tmp))
            st.success(f"Extracted {st.session_state.manual_text_ctx.word_count} words")
    else:
        pasted = st.text_area("Paste lesson text", height=100)
        if st.button("Use this text", use_container_width=True):
            if pasted.strip():
                st.session_state.manual_text_ctx = ext.from_text(pasted)
                st.success("Text loaded!")

    st.markdown("---")
    st.markdown("### Session stats")
    c1, c2 = st.columns(2)
    with c1: st.markdown(f'<div class="stat-card"><div class="stat-value">{session_elapsed()}</div><div class="stat-label">time studied</div></div>', unsafe_allow_html=True)
    with c2: st.markdown(f'<div class="stat-card"><div class="stat-value">{st.session_state.cards_completed}</div><div class="stat-label">cards done</div></div>', unsafe_allow_html=True)
    c3, c4 = st.columns(2)
    with c3: st.markdown(f'<div class="stat-card"><div class="stat-value">{st.session_state.confusion_spikes}</div><div class="stat-label">confusion spikes</div></div>', unsafe_allow_html=True)
    with c4: st.markdown(f'<div class="stat-card"><div class="stat-value">{st.session_state.focus_alerts}</div><div class="stat-label">focus alerts</div></div>', unsafe_allow_html=True)

    st.markdown("---")
    if st.button("⚡ Simulate confusion spike", use_container_width=True):
        st.session_state.confusion_score = 0.85
        trigger_flashcards()
        st.rerun()
    if st.button("👁 Simulate focus lost", use_container_width=True):
        st.session_state.show_focus_alert = True
        st.session_state.focus_alerts += 1
        st.rerun()

# ── Main layout ───────────────────────────────────────────────────────────────
st.markdown("# StudyBuddy")
main_col, cam_col = st.columns([3, 1])

with cam_col:
    st.markdown("### 👁 Attention")
    cam_ph    = st.empty()
    score_ph  = st.empty()
    bar_ph    = st.empty()

    score = st.session_state.confusion_score
    score_ph.markdown(
        f'<span class="score-badge score-{confusion_label(score)}">Confusion: {confusion_label(score)} ({score:.2f})</span>',
        unsafe_allow_html=True
    )
    bar_ph.markdown(f"""
    <div class="conf-bar-wrap">
      <div class="conf-label">Confusion level</div>
      <div class="conf-bar-bg">
        <div class="conf-bar-fill" style="width:{int(score*100)}%; background:{confusion_color(score)};"></div>
      </div>
    </div>""", unsafe_allow_html=True)

    if not WEBCAM_AVAILABLE:
        cam_ph.info("Webcam unavailable.\nUse sidebar buttons to simulate.")

with main_col:
    if st.session_state.show_focus_alert:
        st.markdown("""
        <div class="focus-alert">
          <h3>⚠️ Focus check!</h3>
          <p>You switched away from your study material. Come back — your session is still running.</p>
        </div>""", unsafe_allow_html=True)
        if st.button("I'm back — dismiss"):
            st.session_state.show_focus_alert = False
            st.rerun()
        st.markdown("---")

    # ── Live screen panel ─────────────────────────────────────────────────────
    st.markdown("### 🖥 What you're studying right now")
    live: ScreenContext = ctx_mgr.get_current_context()

    if live and not live.is_empty():
        kw_html     = "".join(f'<span class="screen-kw">{k}</span>' for k in live.topic_keywords[:6])
        topic_title = live.active_window_title or (", ".join(live.topic_keywords[:3]).title() if live.topic_keywords else "Detecting…")
        st.markdown(f"""
        <div class="screen-panel">
          <div class="screen-app">{live.active_app} &nbsp;·&nbsp; {live.source} &nbsp;·&nbsp; {live.word_count} words</div>
          <div class="screen-topic">{topic_title}</div>
          <div>{kw_html}</div>
        </div>""", unsafe_allow_html=True)
        with st.expander("Preview detected text"):
            st.text(live.text[:600] + ("…" if len(live.text) > 600 else ""))
    else:
        st.markdown("""
        <div class="screen-panel" style="text-align:center;padding:32px">
          <div style="font-size:32px;margin-bottom:8px">👀</div>
          <div style="color:#6c7086;font-size:14px">
            Waiting for screen content…<br>Open a textbook, PDF, or study website.<br>
            <span style="font-size:12px">Grant Screen Recording in System Preferences → Privacy & Security.</span>
          </div>
        </div>""", unsafe_allow_html=True)

    st.markdown("---")

    # ── Flashcard panel ───────────────────────────────────────────────────────
    if st.session_state.show_flashcards and st.session_state.study_set:
        ss: StudySet = st.session_state.study_set
        sc: ScreenContext = st.session_state.screen_ctx

        if sc and not sc.is_empty():
            st.markdown(f"## 🎴 Flashcards — from *{sc.active_app}*")
            st.caption(f"Based on what you were reading · Topics: {', '.join(sc.topic_keywords[:4])}")
        else:
            st.markdown("## 🎴 Flashcards")

        st.markdown(f"*{ss.summary}*")

        tab_fc, tab_q = st.tabs(["Flashcards", "Practice questions"])

        with tab_fc:
            cards = ss.flashcards
            if cards:
                idx  = st.session_state.current_card_idx % len(cards)
                card = cards[idx]
                st.markdown(f"""
                <div class="flashcard">
                  <div class="flashcard-term">{card.term}</div>
                  <div class="flashcard-def">{card.definition}</div>
                  <div class="flashcard-hint">💡 {card.hint}</div>
                </div>""", unsafe_allow_html=True)
                st.caption(f"Card {idx+1} of {len(cards)}")
                c1, c2, c3 = st.columns(3)
                with c1:
                    if st.button("← Prev"): st.session_state.current_card_idx = max(0, idx-1); st.rerun()
                with c2:
                    if st.button("✅ Got it!"): st.session_state.cards_completed += 1; st.session_state.current_card_idx = idx+1; st.rerun()
                with c3:
                    if st.button("Next →"): st.session_state.current_card_idx = idx+1; st.rerun()

        with tab_q:
            qs = ss.questions
            if qs:
                qidx = st.session_state.current_q_idx % len(qs)
                q    = qs[qidx]
                st.markdown(f'<div class="mcq-box"><div class="mcq-q">{q.question}</div></div>', unsafe_allow_html=True)
                selected = st.radio("", options=q.options, key=f"q_{qidx}", label_visibility="collapsed")
                if st.button("Submit answer"):
                    st.session_state.answer_submitted = True
                    st.session_state.selected_option  = selected
                if st.session_state.answer_submitted and st.session_state.selected_option:
                    ci = q.options.index(st.session_state.selected_option)
                    if ci == q.correct_index:
                        st.success(f"✅ Correct! {q.explanation}"); st.session_state.cards_completed += 1
                    else:
                        st.error(f"❌ Correct: **{q.correct_answer}**\n\n{q.explanation}")
                    if st.button("Next →"):
                        st.session_state.current_q_idx += 1; st.session_state.answer_submitted = False; st.session_state.selected_option = None; st.rerun()

        if st.button("✕ Close study set"):
            st.session_state.show_flashcards = False; st.rerun()

# ── Webcam loop ───────────────────────────────────────────────────────────────
if WEBCAM_AVAILABLE:
    if st.session_state.detector is None:
        try: st.session_state.detector = ConfusionDetector()
        except Exception as e: st.warning(f"Webcam error: {e}")

    if st.session_state.detector:
        frame_rgb, score = st.session_state.detector.get_frame_annotated()
        if frame_rgb is not None:
            cam_ph.image(frame_rgb, channels="RGB", use_container_width=True)
            st.session_state.confusion_score = score
            cooldown_ok = time.time() - st.session_state.last_spike_t > 30
            if score > 0.72 and cooldown_ok:
                trigger_flashcards()
        time.sleep(0.1)
        st.rerun()