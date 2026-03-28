"""
confusion_test_app.py — stable camera version
Run: streamlit run src/confusion_test_app.py
"""

import streamlit as st
import time

st.set_page_config(page_title="Confusion Detector Test", page_icon="🧠", layout="centered")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
.conf-bar-bg   { background: #e0e0e0; border-radius: 6px; height: 14px; width: 100%; margin-top: 6px; }
.conf-bar-fill { border-radius: 6px; height: 14px; }
.score-badge   { display: inline-block; padding: 6px 18px; border-radius: 20px; font-size: 15px; font-weight: 600; margin-top: 10px; }
.score-low     { background: #d4edda; color: #155724; }
.score-medium  { background: #fff3cd; color: #856404; }
.score-high    { background: #f8d7da; color: #721c24; }
</style>
""", unsafe_allow_html=True)

st.markdown("# 🧠 Confusion Detector Test")
st.markdown("*Webcam only — no flashcards, no screen reading.*")

# ── Import ────────────────────────────────────────────────────────────────────
try:
    from confusion_detector import ConfusionDetector
    WEBCAM_OK = True
except Exception as e:
    WEBCAM_OK = False
    st.error(f"Could not import ConfusionDetector: {e}")

# ── Session state ─────────────────────────────────────────────────────────────
if "detector"        not in st.session_state: st.session_state.detector        = None
if "confusion_score" not in st.session_state: st.session_state.confusion_score = 0.0
if "spike_count"     not in st.session_state: st.session_state.spike_count     = 0
if "running"         not in st.session_state: st.session_state.running         = False

# ── Buttons ───────────────────────────────────────────────────────────────────
col1, col2 = st.columns(2)
with col1:
    if st.button("▶ Start", use_container_width=True, disabled=not WEBCAM_OK):
        if st.session_state.detector is None:
            try:
                st.session_state.detector = ConfusionDetector()
            except Exception as e:
                st.error(f"Webcam error: {e}")
        st.session_state.running = True

with col2:
    if st.button("⏹ Stop", use_container_width=True):
        st.session_state.running = False
        if st.session_state.detector:
            st.session_state.detector.release()
            st.session_state.detector = None

# ── Placeholders (created once, updated in loop) ──────────────────────────────
cam_ph   = st.empty()
score_ph = st.empty()
bar_ph   = st.empty()
spike_ph = st.empty()

st.markdown("""
<div style="display:flex;gap:10px;margin-top:12px">
  <span style="background:#d4edda;color:#155724;border-radius:6px;padding:4px 10px;font-size:12px">0.0–0.4 · calm</span>
  <span style="background:#fff3cd;color:#856404;border-radius:6px;padding:4px 10px;font-size:12px">0.4–0.7 · uncertain</span>
  <span style="background:#f8d7da;color:#721c24;border-radius:6px;padding:4px 10px;font-size:12px">0.7–1.0 · confused</span>
</div>
""", unsafe_allow_html=True)

if not WEBCAM_OK:
    st.warning("Mediapipe/OpenCV not found.")
elif not st.session_state.running:
    st.info("Press **Start** to begin.")

# ── Stable camera loop ────────────────────────────────────────────────────────
if st.session_state.running and st.session_state.detector:
    import cv2
    det = st.session_state.detector
    last_spike_t  = 0
    frame_count   = 0
    score         = 0.0

    while st.session_state.running:
        ret, frame = det.cap.read()
        if not ret:
            break

        frame_count += 1

        # Run MediaPipe every 3rd frame only — keeps video smooth
        if frame_count % 3 == 0:
            score = det.update()

        # Always show the frame
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        cam_ph.image(frame_rgb, channels="RGB", use_container_width=True)

        # Update score UI every 3rd frame too
        if frame_count % 3 == 0:
            color = "#28a745" if score < 0.4 else "#ffc107" if score < 0.7 else "#dc3545"
            label = "low"     if score < 0.4 else "medium"  if score < 0.7 else "high"

            score_ph.markdown(
                f'<span class="score-badge score-{label}">Confusion: {label} &nbsp;|&nbsp; {score:.2f}</span>',
                unsafe_allow_html=True
            )
            bar_ph.markdown(f"""
            <div style="margin-top:8px">
              <div style="font-size:12px;color:#888;margin-bottom:4px">Confusion level</div>
              <div class="conf-bar-bg">
                <div class="conf-bar-fill" style="width:{int(score*100)}%;background:{color};"></div>
              </div>
            </div>""", unsafe_allow_html=True)

            now = time.time()
            if score > 0.72 and (now - last_spike_t) > 5:
                st.session_state.spike_count += 1
                last_spike_t = now
                st.toast(f"Confusion detected! Score: {score:.2f}", icon="🧠")

            spike_ph.markdown(
                f'<div style="font-size:13px;color:#888;margin-top:8px">Spikes detected: <strong>{st.session_state.spike_count}</strong></div>',
                unsafe_allow_html=True
            )