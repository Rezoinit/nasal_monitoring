# nasal_monitor/models.py
# ─────────────────────────────────────────────────
# Data structures for nasal breathing monitoring.
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
    A detected breath event from the adaptive detector.
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
