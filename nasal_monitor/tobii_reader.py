# nasal_monitor/tobii_reader.py
# ─────────────────────────────────────────────────
# Connects to Tobii Pro Glasses 2 over WiFi.
# Streams raw gaze data. No filtering.
#
# HOW TO CONNECT:
#   1. Power on Tobii Recording Unit
#   2. Join Tobii WiFi on your Mac
#   3. Run TobiiReader.discover() to find IP
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
        """
        self.address  = address
        self._tobii:  Optional[TobiiGlassesController] = None
        self._thread: Optional[threading.Thread]        = None
        self._running = False
        self._on_gaze_cb: Optional[Callable] = None

    # ─────────────────────────────────────────────
    # DECORATOR
    # ─────────────────────────────────────────────

    def on_gaze(self, fn: Callable) -> Callable:
        """
        Called for every gaze reading (~50Hz).
        Callback receives: GazeData
        """
        self._on_gaze_cb = fn
        return fn

    # ─────────────────────────────────────────────
    # START / STOP
    # ─────────────────────────────────────────────

    def start(self):
        print(f"[TobiiReader] Connecting to {self.address}...")
        self._tobii = TobiiGlassesController(
            self.address,
            video_scene=False
        )
        self._tobii.start_streaming()
        self._running = True
        self._thread  = threading.Thread(
            target=self._read_loop,
            daemon=True
        )
        self._thread.start()
        print("[TobiiReader] Streaming gaze data.")

    def stop(self):
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
                data = self._tobii.get_data()

                gp = data.get("gp", {}).get("gp", None)
                if gp is None or len(gp) < 2:
                    time.sleep(0.001)
                    continue

                pd_left  = data.get("left_eye",  {}).get("pd", {}).get("pd", -1.0)
                pd_right = data.get("right_eye", {}).get("pd", {}).get("pd", -1.0)
                valid    = data.get("gp", {}).get("s", 1) == 0

                gaze = GazeData(
                    host_time   = time.time(),
                    gaze_x      = float(gp[0]),
                    gaze_y      = float(gp[1]),
                    pupil_left  = float(pd_left)  if pd_left  != -1.0 else -1.0,
                    pupil_right = float(pd_right) if pd_right != -1.0 else -1.0,
                    valid       = valid,
                )

                if self._on_gaze_cb:
                    self._on_gaze_cb(gaze)

                time.sleep(0.005)

            except Exception as e:
                print(f"[TobiiReader] Error: {e}")
                time.sleep(0.1)

    # ─────────────────────────────────────────────
    # HELPER — auto discover Tobii IP
    # ─────────────────────────────────────────────

    @staticmethod
    def discover() -> str:
        print("[TobiiReader] Searching for Tobii on network...")
        try:
            controller = TobiiGlassesController()
            address    = controller.get_address()
            print(f"[TobiiReader] Found Tobii at: {address}")
            return address
        except Exception as e:
            raise RuntimeError(
                f"[TobiiReader] Could not find Tobii: {e}\n"
                "Make sure:\n"
                "  1. Tobii Recording Unit is powered on\n"
                "  2. Mac is connected to Tobii WiFi\n"
                "  3. tobiiglassesctrl is installed"
            )