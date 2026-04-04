# nasal_monitor/models.py
# ─────────────────────────────────────────────────
# Data structures used throughout the library.
# Using dataclasses for clean, typed, printable objects.
# ─────────────────────────────────────────────────

from dataclasses import dataclass
from typing import Optional

@dataclass
class RawReading:
    """
    One raw reading directly from the XIAO board.
    Mirrors exactly the JSON fields in the Arduino sketch.
    """
    timestamp_ms: int        # millis() from board (ms since boot)
    host_time:    float      # time.time() on Mac (Unix timestamp)
    mic1:         int        # yellow mic volume (0–4095)
    mic2:         int        # blue mic volume   (0–4095)
    side:         str        # "left" | "right" | "both" | "none"


@dataclass
class BreathEvent:
    """
    A detected breath event — emitted when
    breathing starts, changes side, or stops.
    """
    host_time:    float      # when it happened (Unix timestamp)
    side:         str        # "left" | "right" | "both" | "none"
    intensity:    float      # 0.0 → 1.0 normalised volume
    mic1_raw:     int        # raw mic1 value for this event
    mic2_raw:     int        # raw mic2 value for this event
    duration_ms:  Optional[float] = None  # filled when breath ends


@dataclass
class GazeData:
    """
    One gaze reading from Tobii Pro Glasses 2.
    gp  = gaze point (x, y) normalised 0.0–1.0
    pd  = pupil diameter in mm (left, right)
    """
    host_time:    float          # Mac clock (time.time())
    gaze_x:       float          # 0.0 = left edge, 1.0 = right edge
    gaze_y:       float          # 0.0 = top,       1.0 = bottom
    pupil_left:   float          # mm, -1 if invalid
    pupil_right:  float          # mm, -1 if invalid
    valid:        bool           # False if Tobii lost eye


@dataclass
class SyncedEvent:
    """
    One fully synchronized event — gaze + breathing
    merged by timestamp within a 50ms window.
    This is the main output of the combined system.
    """
    host_time:        float      # Mac clock when event was created

    # From Tobii
    gaze_x:           float
    gaze_y:           float
    pupil_left:       float
    pupil_right:      float
    gaze_valid:       bool

    # From XIAO mics
    breath_side:      str        # left/right/both/none
    breath_intensity: float      # 0.0–1.0
    mic1_raw:         int
    mic2_raw:         int