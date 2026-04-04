# nasal_monitor/tobii_reader.py
# ─────────────────────────────────────────────────
# Connects to Tobii Pro Glasses 2 over WiFi,
# streams live gaze data, fires callbacks.
#
# HOW TO CONNECT:
#   1. Power on Tobii Recording Unit
#   2. On your Mac: join the Tobii WiFi network
#      (named something like "Tobii_XXXXXX")
#   3. Find IP: check Tobii Controller app
#      OR run: python -c "import tobiiglassesctrl;
#              c = tobiiglassesctrl.TobiiGlassesController();
#              print(c.get_address())"
# ─────────────────────────────────────────────────

import time
import threading
from typing import Callable, Optional
from tobiiglassesctrl import TobiiGlassesController

from .models import GazeData


class TobiiReader:

    def __init__(self, address: str):
        """
        address : IP address of Tobii Recording Unit
                  e.g. "192.168.71.50"
                  Find it in the Tobii Controller app
                  or via auto-discovery below
        """
        self.address  = address
        self._tobii:  Optional[TobiiGlassesController] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

        # Callback registered by user
        self._on_gaze_cb: Optional[Callable] = None

    # ─────────────────────────────────────────────
    # DECORATOR — register your callback
    # ─────────────────────────────────────────────

    def on_gaze(self, fn: Callable) -> Callable:
        """
        Called for every gaze reading (~50Hz from Tobii G2).
        Callback receives: GazeData
        """
        self._on_gaze_cb = fn
        return fn

    # ─────────────────────────────────────────────
    # START / STOP
    # ─────────────────────────────────────────────

    def start(self):
        """Connect to Tobii and begin streaming in background."""
        print(f"[TobiiReader] Connecting to {self.address}...")

        self._tobii = TobiiGlassesController(
            self.address,
            video_scene=False   # we only want gaze, not video stream
        )

        # Start live data stream on Tobii side
        self._tobii.start_streaming()
        self._running = True

        self._thread = threading.Thread(
            target=self._read_loop,
            daemon=True
        )
        self._thread.start()
        print("[TobiiReader] Streaming gaze data.")

    def stop(self):
        """Stop streaming and disconnect."""
        self._running = False
        if self._tobii:
            self._tobii.stop_streaming()
        print("[TobiiReader] Stopped.")

    # ─────────────────────────────────────────────
    # INTERNAL — gaze read loop
    # ─────────────────────────────────────────────

    def _read_loop(self):
        while self._running:
            try:
                # get_data() returns a dict with all live data
                data = self._tobii.get_data()

                # ── Extract gaze point ─────────────────────
                # 'gp' = gaze point [x, y] normalised 0.0-1.0
                gp = data.get("gp", {}).get("l", None)

                # Skip if no valid gaze point yet
                if gp is None or len(gp) < 2:
                    time.sleep(0.001)
                    continue

                # ── Extract pupil diameters ────────────────
                # 'pd' = pupil diameter per eye
                pd_left  = data.get("pd",  {}).get("l", -1.0)
                pd_right = data.get("pd",  {}).get("r", -1.0)

                # ── Extract validity ───────────────────────
                # 'gp3' validity flag
                valid = data.get("gp3", {}).get("l") is not None

                gaze = GazeData(
                    host_time   = time.time(),
                    gaze_x      = float(gp[0]),
                    gaze_y      = float(gp[1]),
                    pupil_left  = float(pd_left)  if pd_left  else -1.0,
                    pupil_right = float(pd_right) if pd_right else -1.0,
                    valid       = valid,
                )

                if self._on_gaze_cb:
                    self._on_gaze_cb(gaze)

                time.sleep(0.005)   # ~100Hz poll rate max

            except Exception as e:
                print(f"[TobiiReader] Error: {e}")
                time.sleep(0.1)

    # ─────────────────────────────────────────────
    # HELPER — auto discover Tobii on network
    # ─────────────────────────────────────────────

    @staticmethod
    def discover() -> str:
        """
        Try to auto-discover Tobii on local network.
        Returns IP address as string.
        Call this if you don't know the IP.
        """
        print("[TobiiReader] Searching for Tobii on network...")
        try:
            controller = TobiiGlassesController()
            address = controller.get_address()
            print(f"[TobiiReader] Found Tobii at: {address}")
            return address
        except Exception as e:
            raise RuntimeError(
                f"[TobiiReader] Could not find Tobii: {e}\n"
                "Make sure:\n"
                "  1. Tobii Recording Unit is powered on\n"
                "  2. Your Mac is connected to Tobii WiFi\n"
                "  3. tobiiglassesctrl is installed"
            )