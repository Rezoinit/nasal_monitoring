"""
gaze_viz/scene_overlay.py
─────────────────────────────────────────────────────────────
Scene camera feed with live gaze overlay.

Shows the first-person scene video from the Tobii glasses with:
  - Gaze circle at current fixation point
  - Pupil diameter for each eye (text overlay)
  - Dynamic pupil size indicator circle (scales with pd)

Requirements:
    pip install opencv-python

Run:
    python gaze_viz/scene_overlay.py
"""

import cv2
import time
import threading
from tobiiglassesctrl import TobiiGlassesController

# ── Config ────────────────────────────────────────
TOBII_IP  = "192.168.71.50"

# Tobii Pro Glasses 2 RTSP scene camera URL.
# Try these in order if the first fails:
#   rtsp://192.168.71.50:8554/live/scene
#   rtsp://192.168.71.50/live/scene
SCENE_URL = f"rtsp://{TOBII_IP}:8554/live/scene"

# ── Shared state ─────────────────────────────────
latest = {
    "gp":    [0.5, 0.5],
    "pd_l":  3.0,
    "pd_r":  3.0,
    "valid": False,
}

# ── Background gaze thread ────────────────────────
tobii = TobiiGlassesController(TOBII_IP, video_scene=False)
tobii.start_streaming()

def _data_loop():
    while True:
        try:
            d = tobii.get_data()
            gp = d.get("gp", {}).get("gp")
            if gp and len(gp) == 2:
                latest["gp"] = gp
            latest["valid"] = d.get("gp", {}).get("s", 1) == 0
            l_pd = d.get("left_eye",  {}).get("pd", {}).get("pd", -1)
            r_pd = d.get("right_eye", {}).get("pd", {}).get("pd", -1)
            if l_pd > 0: latest["pd_l"] = l_pd
            if r_pd > 0: latest["pd_r"] = r_pd
            time.sleep(0.005)
        except Exception:
            time.sleep(0.05)

threading.Thread(target=_data_loop, daemon=True).start()

# ── Scene camera ──────────────────────────────────
cap = cv2.VideoCapture(SCENE_URL)
if not cap.isOpened():
    print(f"[scene_overlay] Could not open: {SCENE_URL}")
    print("Try changing SCENE_URL at the top of this file.")
    tobii.stop_streaming()
    raise SystemExit(1)

print(f"[scene_overlay] Scene camera connected: {SCENE_URL}")
print("[scene_overlay] Press Q to quit.")

# ── Helpers ───────────────────────────────────────
def pd_to_px(pd_mm: float, scale: float = 8.0) -> int:
    """Map pupil diameter (mm) → display circle radius (pixels)."""
    return max(6, int(pd_mm * scale))

FONT       = cv2.FONT_HERSHEY_SIMPLEX
WHITE      = (255, 255, 255)
GREEN      = ( 80, 200,  80)
RED        = ( 60,  60, 220)
GRAY       = (160, 160, 160)
ORANGE     = ( 50, 165, 255)
BLUE       = (230, 100,  40)

# ── Main loop ─────────────────────────────────────
while True:
    ret, frame = cap.read()
    if not ret:
        continue

    h, w = frame.shape[:2]
    gx, gy  = latest["gp"]
    px, py  = int(gx * w), int(gy * h)
    valid   = latest["valid"]
    pd_l    = latest["pd_l"]
    pd_r    = latest["pd_r"]

    dot_color = GREEN if valid else RED

    # ── Gaze marker ───────────────────────────────
    # Outer ring
    cv2.circle(frame, (px, py), 34, dot_color, 2, cv2.LINE_AA)
    # Cross-hair lines
    cv2.line(frame, (px - 42, py), (px - 20, py), dot_color, 1, cv2.LINE_AA)
    cv2.line(frame, (px + 20, py), (px + 42, py), dot_color, 1, cv2.LINE_AA)
    cv2.line(frame, (px, py - 42), (px, py - 20), dot_color, 1, cv2.LINE_AA)
    cv2.line(frame, (px, py + 20), (px, py + 42), dot_color, 1, cv2.LINE_AA)
    # Centre dot
    cv2.circle(frame, (px, py), 4, dot_color, -1, cv2.LINE_AA)

    # ── Pupil size indicators (bottom-left corner) ─
    indicator_y = h - 60
    # Left eye indicator circle
    r_l = pd_to_px(pd_l)
    cv2.circle(frame, (60, indicator_y), r_l, ORANGE, 2, cv2.LINE_AA)
    cv2.putText(frame, f"L  {pd_l:.2f}mm",
                (85, indicator_y + 5), FONT, 0.55, ORANGE, 1, cv2.LINE_AA)
    # Right eye indicator circle
    r_r = pd_to_px(pd_r)
    cv2.circle(frame, (60, indicator_y + 40), r_r, BLUE, 2, cv2.LINE_AA)
    cv2.putText(frame, f"R  {pd_r:.2f}mm",
                (85, indicator_y + 45), FONT, 0.55, BLUE, 1, cv2.LINE_AA)

    # ── Status overlay (top-left) ─────────────────
    label = "VALID" if valid else "GAZE LOST"
    cv2.putText(frame, label, (12, 30), FONT, 0.7, dot_color, 2, cv2.LINE_AA)
    cv2.putText(frame, f"({gx:.3f}, {gy:.3f})",
                (12, 54), FONT, 0.5, GRAY, 1, cv2.LINE_AA)

    cv2.imshow("Tobii Scene — Gaze Overlay  [Q to quit]", frame)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
tobii.stop_streaming()
print("[scene_overlay] Done.")
