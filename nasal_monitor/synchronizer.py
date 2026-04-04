# nasal_monitor/synchronizer.py
# ─────────────────────────────────────────────────
# Merges raw gaze stream (Tobii ~50Hz) with
# raw breathing stream (XIAO ~8Hz) by timestamp.
#
# No thresholds. No classifications.
# Just timestamp alignment of raw values.
# ─────────────────────────────────────────────────

import time
import collections
from typing import Callable, Optional

from .models        import RawReading, GazeData, SyncedEvent
from .reader        import NasalMonitor
from .tobii_reader  import TobiiReader

SYNC_WINDOW_MS = 100   # max ms gap for a valid gaze match


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
            maxlen=200
        )
        self._on_synced_cb: Optional[Callable] = None

        # Wire internal callbacks
        self.tobii.on_gaze(self._store_gaze)
        self.xiao.on_reading(self._sync_and_emit)

    # ─────────────────────────────────────────────
    # DECORATOR
    # ─────────────────────────────────────────────

    def on_event(self, fn: Callable) -> Callable:
        """
        Called for every synchronized raw event (~8Hz).
        Callback receives: SyncedEvent
        """
        self._on_synced_cb = fn
        return fn

    # ─────────────────────────────────────────────
    # START / STOP
    # ─────────────────────────────────────────────

    def start(self):
        self.tobii.start()
        self.xiao.start()
        print("[Synchronizer] Both streams running.")

    def stop(self):
        self.tobii.stop()
        self.xiao.stop()
        print("[Synchronizer] Stopped.")

    def start_blocking(self):
        self.start()
        try:
            while True:
                time.sleep(0.1)
        except KeyboardInterrupt:
            self.stop()

    # ─────────────────────────────────────────────
    # INTERNAL
    # ─────────────────────────────────────────────

    def _store_gaze(self, gaze: GazeData):
        self._gaze_buffer.append(gaze)

    def _sync_and_emit(self, reading: RawReading):
        now       = reading.host_time
        best_gaze = None
        best_diff = float("inf")

        # Find closest gaze reading by timestamp
        for gaze in self._gaze_buffer:
            diff = abs(gaze.host_time - now) * 1000
            if diff < best_diff:
                best_diff = diff
                best_gaze = gaze

        # Build SyncedEvent with raw values only
        if best_gaze and best_diff <= SYNC_WINDOW_MS:
            event = SyncedEvent(
                host_time   = now,
                gaze_x      = best_gaze.gaze_x,
                gaze_y      = best_gaze.gaze_y,
                pupil_left  = best_gaze.pupil_left,
                pupil_right = best_gaze.pupil_right,
                gaze_valid  = best_gaze.valid,
                mic1_raw    = reading.mic1,
                mic2_raw    = reading.mic2,
                seq         = reading.seq,
                board_ms    = reading.timestamp_ms,
                chip_temp_c = reading.chip_temp_c,
            )
        else:
            # No gaze match — record -1 for gaze fields
            event = SyncedEvent(
                host_time   = now,
                gaze_x      = -1.0,
                gaze_y      = -1.0,
                pupil_left  = -1.0,
                pupil_right = -1.0,
                gaze_valid  = False,
                mic1_raw    = reading.mic1,
                mic2_raw    = reading.mic2,
                seq         = reading.seq,
                board_ms    = reading.timestamp_ms,
                chip_temp_c = reading.chip_temp_c,
            )

        if self._on_synced_cb:
            self._on_synced_cb(event)