# nasal_monitor/models.py
# ─────────────────────────────────────────────────
# Data structures used throughout the library.
#
# Philosophy: store everything, decide nothing.
# No thresholds or classifications in these models.
# All signal interpretation happens in analysis.
# ─────────────────────────────────────────────────

from dataclasses import dataclass
from typing      import Optional


@dataclass
class RawReading:
    """
    One raw reading directly from the XIAO board.
    Mirrors exactly the JSON fields in the Arduino sketch.
    No classification — pure sensor values only.
    """
    timestamp_ms:  int      # millis() from board (ms since boot)
    host_time:     float    # time.time() on Mac (Unix timestamp)
    seq:           int      # packet sequence number
    mic1:          int      # yellow mic peak-to-peak (0–4095)
    mic2:          int      # blue mic peak-to-peak   (0–4095)
    chip_temp_c:   float    # chip die temperature in °C


@dataclass
class BreathEvent:
    """
    Optional: a detected breath event from the adaptive detector.
    Used ONLY for real-time live feedback.
    Never affects what gets saved to disk.
    """
    host_time:     float
    board_ms:      int
    seq:           int
    side:          str      # left/right/both/none
    intensity:     float    # 0.0–1.0
    mic1_raw:      int
    mic2_raw:      int
    chip_temp_c:   float
    duration_ms:   Optional[float] = None


@dataclass
class GazeData:
    """
    One gaze reading from Tobii Pro Glasses 2.
    gp = gaze point (x,y) normalised 0.0–1.0
    pd = pupil diameter in mm
    """
    host_time:     float    # Mac clock (time.time())
    gaze_x:        float    # 0.0=left  1.0=right
    gaze_y:        float    # 0.0=top   1.0=bottom
    pupil_left:    float    # mm, -1.0 if invalid
    pupil_right:   float    # mm, -1.0 if invalid
    valid:         bool     # False if Tobii lost the eye


@dataclass
class SyncedEvent:
    """
    One fully synchronized raw event.
    Gaze + breathing merged by timestamp.
    Contains only raw values — no classifications.
    """
    host_time:     float    # Mac clock

    # ── Tobii ─────────────────────────────────────
    gaze_x:        float
    gaze_y:        float
    pupil_left:    float
    pupil_right:   float
    gaze_valid:    bool

    # ── XIAO ──────────────────────────────────────
    mic1_raw:      int      # yellow mic raw value
    mic2_raw:      int      # blue mic raw value
    seq:           int      # packet sequence number
    board_ms:      int      # board millis() timestamp
    chip_temp_c:   float    # chip temperature °C