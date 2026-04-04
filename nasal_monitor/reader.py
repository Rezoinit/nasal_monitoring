# nasal_monitor/reader.py
# ─────────────────────────────────────────────────
# Connects to the XIAO over USB Serial,
# reads JSON lines, parses them, and fires callbacks.
# Runs the serial read loop in a background thread
# so your main Python script stays responsive.
# ─────────────────────────────────────────────────

import json
import time
import threading
import serial
import serial.tools.list_ports
from typing import Callable, Optional

from .models      import RawReading, BreathEvent
from .detector    import BreathDetector


class NasalMonitor:

    def __init__(
        self,
        port:       Optional[str] = None,
        baud:       int           = 115200,
        threshold:  int           = 80,
        mic1_side:   str           = "left",  
        mic2_side:   str           = "right",  
    ):
        """
        mic1_side : which nostril is the yellow wire on? "left" or "right"
        mic2_side : which nostril is the blue wire on?   "left" or "right"
        """
        self.port      = port or self._autodetect_port()
        self.baud      = baud
        self.detector  = BreathDetector(
            threshold  = threshold,
            mic1_side  = mic1_side,   # ← pass down
            mic2_side  = mic2_side,   # ← pass down
        )

        # ── Callback storage ──────────────────────────────
        # Users register functions here via decorators
        self._on_reading_cb: Optional[Callable] = None
        self._on_breath_cb:  Optional[Callable] = None
        self._on_error_cb:   Optional[Callable] = None

        # ── Internal state ────────────────────────────────
        self._serial:  Optional[serial.Serial] = None
        self._thread:  Optional[threading.Thread] = None
        self._running: bool = False

    # ─────────────────────────────────────────────────────
    # DECORATORS — register your callback functions
    # ─────────────────────────────────────────────────────

    def on_reading(self, fn: Callable) -> Callable:
        """
        Called for EVERY raw reading (~8Hz).
        Callback receives: RawReading
        """
        self._on_reading_cb = fn
        return fn

    def on_breath(self, fn: Callable) -> Callable:
        """
        Called only when breath STATE CHANGES.
        (none→left, left→right, right→none etc.)
        Callback receives: BreathEvent
        """
        self._on_breath_cb = fn
        return fn

    def on_error(self, fn: Callable) -> Callable:
        """
        Called if serial connection drops or JSON is malformed.
        Callback receives: Exception
        """
        self._on_error_cb = fn
        return fn

    # ─────────────────────────────────────────────────────
    # START / STOP
    # ─────────────────────────────────────────────────────

    def start(self):
        """
        Open serial port and begin reading in background thread.
        Returns immediately — your script keeps running.
        """
        print(f"[NasalMonitor] Connecting to {self.port}...")

        self._serial  = serial.Serial(self.port, self.baud, timeout=2)
        self._running = True

        # Background thread — reads serial, fires callbacks
        self._thread = threading.Thread(
            target=self._read_loop,
            daemon=True   # dies automatically when main script exits
        )
        self._thread.start()
        print(f"[NasalMonitor] Running. Press Ctrl+C to stop.")

    def stop(self):
        """ Cleanly shut down the serial connection. """
        self._running = False
        if self._serial and self._serial.is_open:
            self._serial.close()
        print("[NasalMonitor] Stopped.")

    def start_blocking(self):
        """
        Same as start() but blocks until Ctrl+C.
        Useful for simple scripts.
        """
        self.start()
        try:
            while True:
                time.sleep(0.1)
        except KeyboardInterrupt:
            self.stop()

    # ─────────────────────────────────────────────────────
    # INTERNAL — serial read loop (runs in background thread)
    # ─────────────────────────────────────────────────────

    def _read_loop(self):
        while self._running:
            try:
                # Read one line from serial
                raw_line = self._serial.readline().decode("utf-8").strip()

                # Skip empty lines and the startup status message
                if not raw_line or "status" in raw_line:
                    continue

                # Parse JSON
                data = json.loads(raw_line)

                # Build RawReading object
                reading = RawReading(
                    timestamp_ms = data["t"],
                    host_time    = time.time(),   # Mac clock
                    mic1         = data["m1"],
                    mic2         = data["m2"],
                    side         = data["s"],
                )

                # Fire raw reading callback
                if self._on_reading_cb:
                    self._on_reading_cb(reading)

                # Run breath detector
                event = self.detector.process(reading)
                if event and self._on_breath_cb:
                    self._on_breath_cb(event)

            except json.JSONDecodeError:
                pass   # skip malformed lines silently

            except Exception as e:
                if self._on_error_cb:
                    self._on_error_cb(e)
                else:
                    print(f"[NasalMonitor] Error: {e}")

    # ─────────────────────────────────────────────────────
    # INTERNAL — auto-detect XIAO serial port
    # ─────────────────────────────────────────────────────

    def _autodetect_port(self) -> str:
        """
        Scans available serial ports and returns the most
        likely XIAO port. Works on macOS and Windows.
        """
        ports = serial.tools.list_ports.comports()

        # macOS: XIAO shows up as /dev/cu.usbmodem...
        for p in ports:
            if "usbmodem" in p.device.lower():
                print(f"[NasalMonitor] Auto-detected port: {p.device}")
                return p.device

        # Windows: look for USB Serial Device
        for p in ports:
            if "USB" in p.description:
                print(f"[NasalMonitor] Auto-detected port: {p.device}")
                return p.device

        raise RuntimeError(
            "[NasalMonitor] XIAO not found. "
            "Pass port= manually e.g. NasalMonitor(port='/dev/cu.usbmodem1101')"
        )