# nasal_monitor/synchronizer.py
# ─────────────────────────────────────────────────
# Merges gaze stream (Tobii, ~50Hz) with
# breathing stream (XIAO, ~8Hz) by timestamp.
#
# Strategy:
#   - Keep a rolling buffer of recent gaze readings
#   - For each breath reading, find the closest
#     gaze reading within SYNC_WINDOW_MS
#   - If found → emit SyncedEvent
#   - If not → emit SyncedEvent with gaze_valid=False
# ─────────────────────────────────────────────────

import time
import collections
from typing import Callable, Optional

from .models      import RawReading, GazeData, SyncedEvent
from .reader      import NasalMonitor
from .tobii_reader import TobiiReader


# Max time difference allowed between gaze + breath (ms)
SYNC_WINDOW_MS = 100


class Synchronizer:

    def __init__(
        self,
        xiao:  NasalMonitor,
        tobii: TobiiReader,
    ):
        self.xiao  = xiao
        self.tobii = tobii

        # Rolling buffer of recent gaze readings (last 2 seconds)
        self._gaze_buffer: collections.deque = collections.deque(
            maxlen=200   # 200 readings @ 100Hz = 2 seconds
        )

        self._on_synced_cb: Optional[Callable] = None

        # Wire up internal callbacks
        self.tobii.on_gaze(self._store_gaze)
        self.xiao.on_reading(self._sync_and_emit)

    # ─────────────────────────────────────────────
    # DECORATOR
    # ─────────────────────────────────────────────

    def on_event(self, fn: Callable) -> Callable:
        """
        Called for every synchronized event (~8Hz).
        Callback receives: SyncedEvent
        """
        self._on_synced_cb = fn
        return fn

    # ─────────────────────────────────────────────
    # START / STOP
    # ─────────────────────────────────────────────

    def start(self):
        """Start both devices simultaneously."""
        self.tobii.start()
        self.xiao.start()
        print("[Synchronizer] Both streams running.")

    def stop(self):
        self.tobii.stop()
        self.xiao.stop()
        print("[Synchronizer] Stopped.")

    def start_blocking(self):
        """Start and block until Ctrl+C."""
        self.start()
        try:
            while True:
                time.sleep(0.1)
        except KeyboardInterrupt:
            self.stop()

    # ─────────────────────────────────────────────
    # INTERNAL — store incoming gaze readings
    # ─────────────────────────────────────────────

    def _store_gaze(self, gaze: GazeData):
        """Called by TobiiReader for every gaze sample."""
        self._gaze_buffer.append(gaze)

    # ─────────────────────────────────────────────
    # INTERNAL — match breath reading to nearest gaze
    # ─────────────────────────────────────────────

    def _sync_and_emit(self, reading: RawReading):
        """Called by NasalMonitor for every breath reading."""

        now = reading.host_time
        best_gaze = None
        best_diff = float("inf")

        # Find closest gaze reading by timestamp
        for gaze in self._gaze_buffer:
            diff = abs(gaze.host_time - now) * 1000   # ms
            if diff < best_diff:
                best_diff = diff
                best_gaze = gaze

        # Calculate breath intensity
        peak    = max(reading.mic1, reading.mic2)
        intensity = min(peak / 400.0, 1.0)

        # Build synced event
        if best_gaze and best_diff <= SYNC_WINDOW_MS:
            # ✅ Good sync — gaze found within time window
            event = SyncedEvent(
                host_time        = now,
                gaze_x           = best_gaze.gaze_x,
                gaze_y           = best_gaze.gaze_y,
                pupil_left       = best_gaze.pupil_left,
                pupil_right      = best_gaze.pupil_right,
                gaze_valid       = best_gaze.valid,
                breath_side      = reading.side,
                breath_intensity = intensity,
                mic1_raw         = reading.mic1,
                mic2_raw         = reading.mic2,
            )
        else:
            # ⚠️ No gaze match — emit with invalid gaze
            event = SyncedEvent(
                host_time        = now,
                gaze_x           = -1.0,
                gaze_y           = -1.0,
                pupil_left       = -1.0,
                pupil_right      = -1.0,
                gaze_valid       = False,
                breath_side      = reading.side,
                breath_intensity = intensity,
                mic1_raw         = reading.mic1,
                mic2_raw         = reading.mic2,
            )

        if self._on_synced_cb:
            self._on_synced_cb(event)