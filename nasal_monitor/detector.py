# nasal_monitor/detector.py
# ─────────────────────────────────────────────────
# OPTIONAL — real-time adaptive breath detector.
#
# This module is used ONLY for live feedback
# during a session (e.g. live plot, LED trigger).
#
# It does NOT affect what gets saved to disk.
# All saved data is always raw and unfiltered.
#
# The adaptive threshold self-calibrates to each
# participant — no manual tuning needed.
# ─────────────────────────────────────────────────

import collections
from typing import Optional
from .models import RawReading, BreathEvent


class BreathDetector:

    def __init__(
        self,
        mic1_side:      str   = "left",
        mic2_side:      str   = "right",
        window_size:    int   = 250,    # readings in baseline window
                                        # 250 × 121ms ≈ 30 seconds
        sensitivity:    float = 2.0,    # std deviations above baseline
        min_breath_ms:  float = 300,    # ignore events < 300ms
    ):
        """
        mic1_side     : nostril yellow wire is on
        mic2_side     : nostril blue wire is on
        window_size   : how many readings to use for baseline
        sensitivity   : how many std devs above baseline = breath
                        lower = more sensitive
                        higher = less sensitive
        min_breath_ms : debounce — ignore very short events
        """
        self.mic1_side     = mic1_side
        self.mic2_side     = mic2_side
        self.sensitivity   = sensitivity
        self.min_breath_ms = min_breath_ms

        # Rolling buffers for adaptive baseline per mic
        self._mic1_buf = collections.deque(maxlen=window_size)
        self._mic2_buf = collections.deque(maxlen=window_size)

        # State tracking
        self._last_side:    str            = "none"
        self._breath_start: Optional[float] = None

    # ─────────────────────────────────────────────
    # Adaptive threshold calculation
    # ─────────────────────────────────────────────

    def _threshold(self, buf: collections.deque) -> float:
        """
        threshold = mean + (sensitivity × std deviation)
        This adapts to each participant automatically.
        Falls back to 80 until enough data collected.
        """
        if len(buf) < 30:
            return 80.0   # fallback until buffer fills (~4 seconds)

        values = list(buf)
        mean   = sum(values) / len(values)
        var    = sum((x - mean) ** 2 for x in values) / len(values)
        std    = var ** 0.5

        return mean + (self.sensitivity * std)

    # ─────────────────────────────────────────────

    def process(self, reading: RawReading) -> Optional[BreathEvent]:
        """
        Feed one RawReading in.
        Returns BreathEvent if breath state changed,
        otherwise returns None.
        """
        # Always add to baseline buffers
        self._mic1_buf.append(reading.mic1)
        self._mic2_buf.append(reading.mic2)

        # Adaptive threshold per mic
        thresh1 = self._threshold(self._mic1_buf)
        thresh2 = self._threshold(self._mic2_buf)

        # Classify using adaptive thresholds
        b1 = reading.mic1 >= thresh1
        b2 = reading.mic2 >= thresh2

        if b1 and b2:
            current_side = "both"
        elif b1:
            current_side = self.mic1_side
        elif b2:
            current_side = self.mic2_side
        else:
            current_side = "none"

        # Intensity — how far above threshold (0.0–1.0)
        i1 = max(0.0, (reading.mic1 - thresh1) / thresh1)
        i2 = max(0.0, (reading.mic2 - thresh2) / thresh2)
        intensity = round(min(max(i1, i2), 1.0), 3)

        # State change detection
        if current_side == self._last_side:
            return None   # no change — nothing to report

        # Debounce — ignore breath endings that are too short
        if (current_side == "none"
                and self._last_side != "none"
                and self._breath_start is not None):
            duration = (reading.host_time - self._breath_start) * 1000
            if duration < self.min_breath_ms:
                self._last_side = current_side
                return None   # too short — ignore

        # Build event
        event = BreathEvent(
            host_time   = reading.host_time,
            board_ms    = reading.timestamp_ms,
            seq         = reading.seq,
            side        = current_side,
            intensity   = intensity,
            mic1_raw    = reading.mic1,
            mic2_raw    = reading.mic2,
            chip_temp_c = reading.chip_temp_c,
        )

        # Add duration if breath just ended
        if current_side == "none" and self._breath_start is not None:
            event.duration_ms = (
                reading.host_time - self._breath_start
            ) * 1000

        # Track breath start
        if current_side != "none":
            self._breath_start = reading.host_time

        self._last_side = current_side
        return event

    # ─────────────────────────────────────────────
    # Diagnostics — useful during development
    # ─────────────────────────────────────────────

    def current_thresholds(self) -> dict:
        """Return current adaptive thresholds for both mics."""
        return {
            "mic1_threshold": round(self._threshold(self._mic1_buf), 1),
            "mic2_threshold": round(self._threshold(self._mic2_buf), 1),
        }