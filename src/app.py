"""
StudyBuddy — Main Streamlit App
Run: streamlit run app.py
"""

import os
import time
import streamlit as st

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="StudyBuddy",
    page_icon="📖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Styling ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@500;700&family=DM+Sans:wght@400;500;600&display=swap');

:root {
  --clockwork: #721B06;
  --cedar: #7C7948;
  --deep-olive: #444210;
  --cafe-noir: #443222;
  --weathered: #888676;
  --linen: #F7F5F3;
  --mauve: #755151;
}

html, body, [class*="css"] {
  font-family: 'DM Sans', sans-serif;
  background-color: var(--linen);
}

h1, h2, h3 { font-family: 'Playfair Display', serif; color: var(--clockwork); }

.flashcard {
  background: white;
  border: 1.5px solid rgba(114,27,6,0.15);
  border-radius: 14px;
  padding: 20px 24px;
  margin-bottom: 12px;
  cursor: pointer;
  transition: all 0.2s;
}
.flashcard:hover { border-color: var(--clockwork); transform: translateY(-2px); box-shadow: 0 4px 16px rgba(114,27,6,0.1); }
.flashcard-front { font-size: 16px; font-weight: 600; color: var(--cafe-noir); }
.flashcard-back  { font-size: 14px; color: var(--weathered); margin-top: 10px; padding-top: 10px; border-top: 1px solid rgba(114,27,6,0.1); }
.flashcard-hint  { font-size: 12px; color: var(--cedar); margin-top: 8px; font-style: italic; }

.score-badge { display: inline-block; padding: 6px 18px; border-radius: 20px; font-size: 14px; font-weight: 600; }
.score-low    { background: #d4edda; color: #155724; }
.score-medium { background: #fff3cd; color: #856404; }
.score-high   { background: #f8d7da; color: #721c24; }

.stat-card { background: white; border: 1.5px solid rgba(114,27,6,0.12); border-radius: 10px; padding: 16px; text-align: center; }
.stat-val  { font-family: 'Playfair Display', serif; font-size: 32px; color: var(--clockwork); }
.stat-lbl  { font-size: 12px; color: var(--weathered); margin-top: 4px; }

.section-divider { height: 1px; background: rgba(114,27,6,0.12); margin: 20px 0; }

.lang-banner { background: white; border: 1.5px solid rgba(114,27,6,0.15); border-radius: 10px; padding: 12px 16px; margin-bottom: 16px; font-size: 13px; color: var(--weathered); }
</style>
""", unsafe_allow_html=True)

# ── API key ───────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# ── Imports ───────────────────────────────────────────────────────────────────
try:
    from flashcards import GeminiFlashcardGenerator
    from text_extractor import TextExtractor
    FLASHCARDS_OK = True
except Exception as e:
    FLASHCARDS_OK = False

try:
    from language import LanguageManager, LANGUAGES
    LANG_OK = True
except Exception as e:
    LANG_OK = False

try:
    from confusion_detector import ConfusionDetector
    WEBCAM_OK = True
except Exception:
    WEBCAM_OK = False

# ── Session state ─────────────────────────────────────────────────────────────
defaults = {
    "study_set": None,
    "translated_set": None,
    "language": "en",
    "confusion_score": 0.0,
    "spike_count": 0,
    "detector": None,
    "running": False,
    "show_backs": {},
    "cards_done": 0,
    "lang_manager": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Init managers ─────────────────────────────────────────────────────────────
if LANG_OK and st.session_state.lang_manager is None and GEMINI_API_KEY:
    st.session_state.lang_manager = LanguageManager(api_key=GEMINI_API_KEY)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📖 StudyBuddy")
    st.markdown("*Focus · Learn · Grow*")
    st.markdown("---")

    # ── Language selector ─────────────────────────────────────────────────────
    st.markdown("### 🌐 Language")
    if LANG_OK:
        lang_options = LanguageManager.get_language_options()
        lang_codes   = [c for c, _ in lang_options]
        lang_labels  = [l for _, l in lang_options]
        selected_idx = lang_codes.index(st.session_state.language) if st.session_state.language in lang_codes else 0
        chosen = st.selectbox("Study in:", lang_labels, index=selected_idx, label_visibility="collapsed")
        chosen_code = lang_codes[lang_labels.index(chosen)]

        if chosen_code != st.session_state.language:
            st.session_state.language = chosen_code
            # Re-translate existing study set if one exists
            if st.session_state.study_set and st.session_state.lang_manager:
                with st.spinner("Translating..."):
                    if chosen_code == "en":
                        st.session_state.translated_set = None
                    else:
                        st.session_state.translated_set = st.session_state.lang_manager.translate_study_set(
                            st.session_state.study_set, chosen_code
                        )
                st.rerun()
    else:
        st.info("Language module not loaded")

    st.markdown("---")

    # ── Session stats ─────────────────────────────────────────────────────────
    st.markdown("### 📊 Session Stats")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f'<div class="stat-card"><div class="stat-val">{st.session_state.spike_count}</div><div class="stat-lbl">confusion spikes</div></div>', unsafe_allow_html=True)
    with col2:
        st.markdown(f'<div class="stat-card"><div class="stat-val">{st.session_state.cards_done}</div><div class="stat-lbl">cards done</div></div>', unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### 🔑 API Key")
    api_input = st.text_input("Gemini API Key", value=GEMINI_API_KEY, type="password", label_visibility="collapsed")
    if api_input:
        GEMINI_API_KEY = api_input
        os.environ["GEMINI_API_KEY"] = api_input

# ── Main content ──────────────────────────────────────────────────────────────
st.markdown("# 📖 StudyBuddy")
st.markdown("*Your AI-powered study companion*")

tab1, tab2, tab3 = st.tabs(["🃏 Flashcards", "🧠 Confusion Detector", "🌐 Translate"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — FLASHCARDS
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.markdown("### Generate Flashcards")

    input_method = st.radio("Input method:", ["Paste text", "Demo topic"], horizontal=True)

    if input_method == "Paste text":
        user_text = st.text_area(
            "Paste your study material here:",
            height=160,
            placeholder="Paste lecture notes, textbook content, or any study material..."
        )
    else:
        demo_topic = st.selectbox("Choose a demo topic:", ["photosynthesis", "newton_laws"])
        user_text = None

    confusion_override = st.slider(
        "Confusion level (affects flashcard difficulty):",
        0.0, 1.0,
        float(st.session_state.confusion_score),
        0.05,
        help="0 = calm, 1 = very confused. Auto-set by webcam detector."
    )

    if st.button("✨ Generate Flashcards", type="primary", use_container_width=True):
        if not GEMINI_API_KEY:
            st.error("Please enter your Gemini API key in the sidebar!")
        elif not FLASHCARDS_OK:
            st.error("Flashcard module not loaded correctly.")
        else:
            with st.spinner("Generating flashcards..."):
                try:
                    ext = TextExtractor()
                    if input_method == "Paste text" and user_text and user_text.strip():
                        ctx = ext.from_text(user_text, source_type="web")
                    else:
                        ctx = ext.demo_text(demo_topic if input_method == "Demo topic" else "photosynthesis")

                    gen = GeminiFlashcardGenerator(api_key=GEMINI_API_KEY)
                    study_set = gen.generate(ctx, confusion_score=confusion_override, num_flashcards=5, num_questions=3)
                    st.session_state.study_set = study_set
                    st.session_state.translated_set = None
                    st.session_state.show_backs = {}

                    # Translate if non-English selected
                    if st.session_state.language != "en" and st.session_state.lang_manager:
                        with st.spinner(f"Translating to {LANGUAGES[st.session_state.language]['name']}..."):
                            st.session_state.translated_set = st.session_state.lang_manager.translate_study_set(
                                study_set, st.session_state.language
                            )
                    st.success("Done!")
                except Exception as e:
                    st.error(f"Error: {e}")

    # ── Display flashcards ────────────────────────────────────────────────────
    active_set = st.session_state.translated_set or st.session_state.study_set

    if active_set:
        lang = st.session_state.language
        if lang != "en" and LANG_OK:
            lang_name = LANGUAGES.get(lang, {}).get("name", lang)
            st.markdown(f'<div class="lang-banner">🌐 Showing content in <strong>{lang_name}</strong></div>', unsafe_allow_html=True)

        if active_set.summary:
            st.markdown("#### 📝 Summary")
            st.info(active_set.summary)

        st.markdown("#### 🃏 Flashcards")
        st.caption("Click a card to flip it!")

        for i, fc in enumerate(active_set.flashcards):
            show_back = st.session_state.show_backs.get(i, False)
            with st.container():
                if st.button(f"Card {i+1}: {fc.term[:60]}{'...' if len(fc.term)>60 else ''}", key=f"fc_{i}", use_container_width=True):
                    st.session_state.show_backs[i] = not show_back
                    if not show_back:
                        st.session_state.cards_done += 1
                    st.rerun()

                if show_back:
                    hint_html = f'<div class="flashcard-hint">💡 {fc.hint}</div>' if fc.hint else ""
                    st.markdown(f'<div class="flashcard"><div class="flashcard-front">Q: {fc.term}</div><div class="flashcard-back">A: {fc.definition}</div>{hint_html}</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — CONFUSION DETECTOR
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown("### 🧠 Confusion Detector")

    if not WEBCAM_OK:
        st.warning("OpenCV / MediaPipe not installed. Run: `pip install opencv-python mediapipe`")
    else:
        col1, col2 = st.columns(2)
        with col1:
            if st.button("▶ Start Camera", use_container_width=True, disabled=st.session_state.running):
                if st.session_state.detector is None:
                    try:
                        st.session_state.detector = ConfusionDetector()
                        st.session_state.running = True
                        st.rerun()
                    except Exception as e:
                        st.error(f"Camera error: {e}")
        with col2:
            if st.button("⏹ Stop", use_container_width=True, disabled=not st.session_state.running):
                st.session_state.running = False
                if st.session_state.detector:
                    st.session_state.detector.release()
                    st.session_state.detector = None
                st.rerun()

        cam_ph   = st.empty()
        score_ph = st.empty()
        bar_ph   = st.empty()

        if st.session_state.running and st.session_state.detector:
            import cv2
            det = st.session_state.detector
            last_spike_t = 0
            frame_count  = 0

            while st.session_state.running:
                ret, frame = det.cap.read()
                if not ret:
                    break
                frame_count += 1
                if frame_count % 3 == 0:
                    score = det.update()
                    st.session_state.confusion_score = score

                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                cam_ph.image(frame_rgb, channels="RGB", use_container_width=True)

                if frame_count % 3 == 0:
                    color = "#28a745" if score < 0.4 else "#ffc107" if score < 0.7 else "#dc3545"
                    label = "low" if score < 0.4 else "medium" if score < 0.7 else "high"
                    score_ph.markdown(f'<span class="score-badge score-{label}">Confusion: {label} &nbsp;|&nbsp; {score:.2f}</span>', unsafe_allow_html=True)
                    bar_ph.markdown(f"""
                    <div style="margin-top:8px">
                      <div style="background:#e0e0e0;border-radius:6px;height:10px;">
                        <div style="width:{int(score*100)}%;background:{color};border-radius:6px;height:10px;transition:width 0.3s;"></div>
                      </div>
                    </div>""", unsafe_allow_html=True)

                    now = time.time()
                    if score > 0.72 and (now - last_spike_t) > 5:
                        st.session_state.spike_count += 1
                        last_spike_t = now
                        st.toast("Confusion detected! Go to Flashcards tab to study.", icon="🧠")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — TRANSLATE
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.markdown("### 🌐 Translate Study Material")
    st.markdown("Paste any text and get it explained in your language.")

    if not LANG_OK:
        st.error("Language module not loaded.")
    else:
        translate_text = st.text_area(
            "Text to translate / explain:",
            height=160,
            placeholder="Paste lecture notes, a confusing paragraph, anything..."
        )

        target_lang_options = LanguageManager.get_language_options()
        target_labels = [l for _, l in target_lang_options]
        target_codes  = [c for c, _ in target_lang_options]
        chosen_label  = st.selectbox("Translate to:", target_labels)
        chosen_code   = target_codes[target_labels.index(chosen_label)]

        if st.button("🌐 Translate & Explain", type="primary", use_container_width=True):
            if not GEMINI_API_KEY:
                st.error("Please enter your Gemini API key in the sidebar!")
            elif not translate_text.strip():
                st.warning("Please paste some text first!")
            else:
                with st.spinner("Translating..."):
                    try:
                        import google.generativeai as genai
                        genai.configure(api_key=GEMINI_API_KEY)
                        model = genai.GenerativeModel("gemini-1.5-flash")

                        lang_name = LANGUAGES.get(chosen_code, {}).get("name", chosen_code)

                        prompt = f"""You are a helpful study assistant.

A student needs this content explained and translated into {lang_name}.

Please:
1. Give a brief plain-English summary (2-3 sentences)
2. Then provide the full translation into {lang_name}

Content:
{translate_text[:4000]}"""

                        response = model.generate_content(prompt)
                        st.success("Done!")
                        st.markdown("#### Result")
                        st.markdown(response.text)

                    except Exception as e:
                        st.error(f"Translation error: {e}")
