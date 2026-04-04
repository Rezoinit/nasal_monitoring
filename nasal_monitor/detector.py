# nasal_monitor/detector.py
# ─────────────────────────────────────────────────
# Watches the stream of RawReadings and decides
# when a breath event starts, continues, or ends.
# ─────────────────────────────────────────────────

import time
from .models import RawReading, BreathEvent

# Max volume we expect — used to normalise 0.0→1.0
MAX_VOLUME = 400


class BreathDetector:

    def __init__(
            self,
        threshold:  int = 80,
        mic1_side:  str = "left",  
        mic2_side:  str = "right",  
    ):
        """
        threshold : minimum mic volume that counts as a breath.
                    Raise if false triggers. Lower if breath missed.
        """
        self.threshold  = threshold
        self.mic1_side  = mic1_side
        self.mic2_side  = mic2_side
        self._last_side = "none"
        self._breath_start = None

    def process(self, reading: RawReading) -> BreathEvent | None:

        b1 = reading.mic1 >= self.threshold
        b2 = reading.mic2 >= self.threshold

        # Determine side using configurable assignment
        if b1 and b2:
            current_side = "both"
        elif b1:
            current_side = self.mic1_side   # ← dynamic
        elif b2:
            current_side = self.mic2_side   # ← dynamic
        else:
            current_side = "none"
            
        """
        Feed one RawReading in.
        Returns a BreathEvent if something noteworthy happened,
        otherwise returns None.
        """
        current_side = reading.side

        # ── Calculate normalised intensity ────────────────
        peak_vol   = max(reading.mic1, reading.mic2)
        intensity  = min(peak_vol / MAX_VOLUME, 1.0)

        # ── Detect state change ───────────────────────────
        if current_side != self._last_side:

            event = BreathEvent(
                host_time   = reading.host_time,
                side        = current_side,
                intensity   = intensity,
                mic1_raw    = reading.mic1,
                mic2_raw    = reading.mic2,
            )

            # If a breath just ended, add how long it lasted
            if self._last_side != "none" and current_side == "none":
                if self._breath_start:
                    event.duration_ms = (
                        reading.host_time - self._breath_start
                    ) * 1000

            # Track when this breath started
            if current_side != "none":
                self._breath_start = reading.host_time

            self._last_side = current_side
            return event

        return None   # no state change — nothing to report