"""
Module 1: Confusion Detector
Uses webcam + MediaPipe to compute a 0.0-1.0 confusion score from:
  - Blink rate (low blinks = zoned out / high = stressed)
  - Head pose (looking away = confused/distracted)
  - Gaze deviation (eyes drifting off-center)

Usage:
    detector = ConfusionDetector()
    score = detector.get_score()   # call in a loop
    detector.release()
"""

import cv2
import mediapipe as mp
import numpy as np
import time
from collections import deque


# ── MediaPipe landmarks ────────────────────────────────────────────────────────
LEFT_EYE  = [362, 385, 387, 263, 373, 380]
RIGHT_EYE = [33,  160, 158, 133, 153, 144]
LEFT_IRIS  = [474, 475, 476, 477]
RIGHT_IRIS = [469, 470, 471, 472]
NOSE_TIP   = 1
CHIN       = 152
LEFT_EAR   = 234
RIGHT_EAR  = 454


def eye_aspect_ratio(landmarks, indices, img_w, img_h):
    pts = np.array([
        [landmarks[i].x * img_w, landmarks[i].y * img_h]
        for i in indices
    ])
    # vertical distances
    A = np.linalg.norm(pts[1] - pts[5])
    B = np.linalg.norm(pts[2] - pts[4])
    # horizontal distance
    C = np.linalg.norm(pts[0] - pts[3])
    return (A + B) / (2.0 * C + 1e-6)


def iris_deviation(landmarks, iris_indices, eye_indices, img_w, img_h):
    """How far the iris center is from the eye center (0=centered, 1=far)."""
    iris_pts = np.array([
        [landmarks[i].x * img_w, landmarks[i].y * img_h]
        for i in iris_indices
    ])
    eye_pts = np.array([
        [landmarks[i].x * img_w, landmarks[i].y * img_h]
        for i in eye_indices
    ])
    iris_center = iris_pts.mean(axis=0)
    eye_center  = eye_pts.mean(axis=0)
    eye_width   = np.linalg.norm(eye_pts[0] - eye_pts[3]) + 1e-6
    return np.linalg.norm(iris_center - eye_center) / eye_width


class ConfusionDetector:
    def __init__(self, window_seconds=10, camera_index=0):
        self.mp_face = mp.solutions.face_mesh
        self.face_mesh = self.mp_face.FaceMesh(
            refine_landmarks=True,
            max_num_faces=1,
            min_detection_confidence=0.6,
            min_tracking_confidence=0.6
        )
        self.cap = cv2.VideoCapture(camera_index)

        # Rolling history
        ws = window_seconds * 30  # assume ~30fps
        self.ear_history    = deque(maxlen=ws)
        self.gaze_history   = deque(maxlen=ws)
        self.pose_history   = deque(maxlen=ws)
        self.blink_times    = deque(maxlen=50)

        self._in_blink      = False
        self._last_frame_t  = time.time()
        self.score          = 0.0

        # Baseline EAR (calibrated on first 60 frames)
        self._baseline_ear  = None
        self._calibration   = deque(maxlen=60)

    # ── Main update (call every frame) ────────────────────────────────────────
    def update(self):
        ret, frame = self.cap.read()
        if not ret:
            return self.score

        h, w = frame.shape[:2]
        rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = self.face_mesh.process(rgb)

        if not result.multi_face_landmarks:
            # No face detected → high confusion signal
            self.score = 0.8
            return self.score

        lm = result.multi_face_landmarks[0].landmark

        # ── EAR & Blink ───────────────────────────────────────────────────────
        left_ear  = eye_aspect_ratio(lm, LEFT_EYE,  w, h)
        right_ear = eye_aspect_ratio(lm, RIGHT_EYE, w, h)
        ear = (left_ear + right_ear) / 2.0

        # Calibration
        if self._baseline_ear is None:
            self._calibration.append(ear)
            if len(self._calibration) == 60:
                self._baseline_ear = np.mean(self._calibration)
        else:
            blink_threshold = self._baseline_ear * 0.65
            if ear < blink_threshold and not self._in_blink:
                self._in_blink = True
            elif ear >= blink_threshold and self._in_blink:
                self._in_blink = False
                self.blink_times.append(time.time())

        self.ear_history.append(ear)

        # ── Gaze deviation ────────────────────────────────────────────────────
        left_gaze  = iris_deviation(lm, LEFT_IRIS,  LEFT_EYE,  w, h)
        right_gaze = iris_deviation(lm, RIGHT_IRIS, RIGHT_EYE, w, h)
        gaze_dev   = (left_gaze + right_gaze) / 2.0
        self.gaze_history.append(gaze_dev)

        # ── Head pose (yaw proxy via ear landmark ratio) ──────────────────────
        nose  = np.array([lm[NOSE_TIP].x * w, lm[NOSE_TIP].y * h])
        l_ear = np.array([lm[LEFT_EAR].x  * w, lm[LEFT_EAR].y  * h])
        r_ear = np.array([lm[RIGHT_EAR].x * w, lm[RIGHT_EAR].y * h])
        face_width  = np.linalg.norm(l_ear - r_ear) + 1e-6
        nose_offset = abs(nose[0] - (l_ear[0] + r_ear[0]) / 2) / face_width
        self.pose_history.append(nose_offset)

        self.score = self._compute_score()
        return self.score

    def _compute_score(self):
        if len(self.ear_history) < 10:
            return 0.0

        # ── Blink rate signal ─────────────────────────────────────────────────
        now = time.time()
        recent_blinks = sum(1 for t in self.blink_times if now - t < 60)
        # Normal = 15-20 blinks/min. Very low (<8) or very high (>25) → confused
        if recent_blinks < 8:
            blink_score = 0.7   # zoned out
        elif recent_blinks > 25:
            blink_score = 0.6   # stressed/overwhelmed
        else:
            blink_score = 0.1   # normal range

        # ── Gaze deviation signal ─────────────────────────────────────────────
        avg_gaze = np.mean(list(self.gaze_history)[-30:])
        gaze_score = min(avg_gaze / 0.35, 1.0)   # normalize; 0.35 = "looking away"

        # ── Head pose signal ──────────────────────────────────────────────────
        avg_pose = np.mean(list(self.pose_history)[-30:])
        pose_score = min(avg_pose / 0.25, 1.0)   # normalize; 0.25 = clearly turned

        # ── Weighted combination ──────────────────────────────────────────────
        score = 0.35 * blink_score + 0.40 * gaze_score + 0.25 * pose_score
        return round(float(np.clip(score, 0.0, 1.0)), 3)

    def get_score(self):
        """Convenience: update then return score."""
        return self.update()

    def get_frame_annotated(self):
        """Returns the current frame with score overlay (for Streamlit display)."""
        ret, frame = self.cap.read()
        if not ret:
            return None, self.score
        score = self.update()
        # Overlay
        color = (0, 200, 100) if score < 0.4 else (0, 165, 255) if score < 0.7 else (0, 0, 220)
        cv2.putText(frame, f"Confusion: {score:.2f}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
        bar_w = int(score * 200)
        cv2.rectangle(frame, (10, 45), (210, 60), (50, 50, 50), -1)
        cv2.rectangle(frame, (10, 45), (10 + bar_w, 60), color, -1)
        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), score

    def release(self):
        self.cap.release()


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Starting confusion detector — press Q to quit")
    det = ConfusionDetector()
    while True:
        frame_rgb, score = det.get_frame_annotated()
        if frame_rgb is None:
            break
        bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
        cv2.imshow("Confusion Detector", bgr)
        print(f"\rScore: {score:.3f}", end="", flush=True)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    det.release()
    cv2.destroyAllWindows()