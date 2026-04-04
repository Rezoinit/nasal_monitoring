# nasal_monitor/reader.py
# ─────────────────────────────────────────────────
# Connects to XIAO over USB Serial.
# Reads JSON, fires callbacks.
# Runs in background thread.
#
# IMPORTANT — Two strictly separate layers:
#
# Layer 1 — RAW DATA (always active)
#   on_reading callback fires for every packet
#   This is your data — never filtered
#
# Layer 2 — LIVE DETECTION (opt-in only)
#   Only active if live_detection=True
#   Used ONLY for real-time feedback
#   Completely invisible to raw data layer
# ─────────────────────────────────────────────────

import json
import time
import threading
import serial
import serial.tools.list_ports
from typing import Callable, Optional

from .models   import RawReading, BreathEvent
from .detector import BreathDetector


class NasalMonitor:

    def __init__(
        self,
        port:           Optional[str]  = None,
        baud:           int            = 115200,
        mic1_side:      str            = "left",
        mic2_side:      str            = "right",
        live_detection: bool           = False,
        sensitivity:    float          = 2.0,
        min_breath_ms:  float          = 300,
    ):
        """
        port           : serial port, None = auto-detect
        baud           : must match Arduino (115200)
        mic1_side      : nostril yellow wire is on
        mic2_side      : nostril blue wire is on

        live_detection : DEFAULT FALSE
                         Set True ONLY if you need real-time
                         breath events for live feedback.
                         Has ZERO effect on raw data recording.
                         Raw data always flows at full fidelity.

        sensitivity    : only used if live_detection=True
        min_breath_ms  : only used if live_detection=True
        """
        self.port = port or self._autodetect_port()
        self.baud = baud

        # ── Live detector — completely isolated ───
        # Never touches raw data layer
        # Never affects what gets saved
        self._detector: Optional[BreathDetector] = None
        if live_detection:
            self._detector = BreathDetector(
                mic1_side     = mic1_side,
                mic2_side     = mic2_side,
                sensitivity   = sensitivity,
                min_breath_ms = min_breath_ms,
            )

        # ── Callbacks ─────────────────────────────
        self._on_reading_cb: Optional[Callable] = None
        self._on_breath_cb:  Optional[Callable] = None
        self._on_error_cb:   Optional[Callable] = None

        # ── Time anchor ───────────────────────────
        self._anchor_host:  Optional[float] = None
        self._anchor_board: Optional[int]   = None

        # ── Packet integrity tracking ─────────────
        self._last_seq: int = 0
        self._dropped:  int = 0

        # ── Internal ──────────────────────────────
        self._serial:  Optional[serial.Serial]    = None
        self._thread:  Optional[threading.Thread]  = None
        self._running: bool = False

    # ─────────────────────────────────────────────
    # DECORATORS
    # ─────────────────────────────────────────────

    def on_reading(self, fn: Callable) -> Callable:
        """
        Fires for EVERY raw reading (~8Hz).
        Always active — unaffected by live_detection.
        Callback receives: RawReading
        """
        self._on_reading_cb = fn
        return fn

    def on_breath(self, fn: Callable) -> Callable:
        """
        Fires when breath state changes.
        ONLY active if live_detection=True.
        NEVER affects raw data.
        Callback receives: BreathEvent
        """
        self._on_breath_cb = fn
        return fn

    def on_error(self, fn: Callable) -> Callable:
        """
        Fires on serial or parse errors.
        Callback receives: Exception
        """
        self._on_error_cb = fn
        return fn

    # ─────────────────────────────────────────────
    # PUBLIC PROPERTIES
    # ─────────────────────────────────────────────

    @property
    def dropped_packets(self) -> int:
        return self._dropped

    @property
    def current_thresholds(self) -> Optional[dict]:
        """
        Current adaptive thresholds.
        Returns None if live_detection=False.
        For monitoring only — never applied to raw data.
        """
        if self._detector:
            return self._detector.current_thresholds()
        return None

    def board_to_host_time(self, board_ms: int) -> Optional[float]:
        """
        Convert board millis() to real-world Unix time.
        Returns None if anchor not yet established.
        """
        if self._anchor_host is None:
            return None
        return self._anchor_host + (
            board_ms - self._anchor_board
        ) / 1000.0

    # ─────────────────────────────────────────────
    # START / STOP
    # ─────────────────────────────────────────────

    def start(self):
        print(f"[NasalMonitor] Connecting to {self.port}...")
        self._serial  = serial.Serial(self.port, self.baud, timeout=2)
        self._running = True
        self._thread  = threading.Thread(
            target=self._read_loop,
            daemon=True
        )
        self._thread.start()
        mode = "raw data mode"
        if self._detector:
            mode = "raw data mode + live detection (feedback only)"
        print(f"[NasalMonitor] Running — {mode}")

    def stop(self):
        self._running = False
        if self._serial and self._serial.is_open:
            self._serial.close()
        print(
            f"[NasalMonitor] Stopped. "
            f"Dropped packets: {self._dropped}"
        )

    def start_blocking(self):
        self.start()
        try:
            while True:
                time.sleep(0.1)
        except KeyboardInterrupt:
            self.stop()

    # ─────────────────────────────────────────────
    # INTERNAL — serial read loop
    # ─────────────────────────────────────────────

    def _read_loop(self):
        while self._running:
            try:
                raw_line = (
                    self._serial.readline()
                    .decode("utf-8")
                    .strip()
                )
                if not raw_line:
                    continue

                data = json.loads(raw_line)

                # ── Startup message ───────────────
                if "status" in data:
                    print(
                        f"[NasalMonitor] Board ready. "
                        f"boot_ms={data.get('boot_ms', '?')}"
                    )
                    continue

                # ── Build RawReading ──────────────
                host_now = time.time()
                reading  = RawReading(
                    timestamp_ms = data["t"],
                    host_time    = host_now,
                    seq          = data["seq"],
                    mic1         = data["m1"],
                    mic2         = data["m2"],
                    chip_temp_c  = data["temp"] / 4.0,
                )

                # ── Establish time anchor ─────────
                if self._anchor_host is None:
                    self._anchor_host  = host_now
                    self._anchor_board = reading.timestamp_ms
                    print(
                        f"[NasalMonitor] Time anchor set. "
                        f"board_ms={reading.timestamp_ms} "
                        f"host={host_now:.3f}"
                    )

                # ── Dropped packet check ──────────
                if self._last_seq > 0:
                    gap = reading.seq - self._last_seq
                    if gap > 1:
                        self._dropped += gap - 1
                        print(
                            f"[NasalMonitor] ⚠️  "
                            f"{gap-1} packet(s) dropped "
                            f"(seq {self._last_seq}"
                            f"→{reading.seq})"
                        )
                self._last_seq = reading.seq

                # ── RAW DATA LAYER ────────────────
                # Always fires. This is your data.
                # No filtering. No decisions.
                if self._on_reading_cb:
                    self._on_reading_cb(reading)

                # ── LIVE DETECTION LAYER ──────────
                # Completely separate pipeline.
                # Only runs if live_detection=True.
                # Zero effect on raw data above.
                if self._detector:
                    event = self._detector.process(reading)
                    if event and self._on_breath_cb:
                        self._on_breath_cb(event)

            except json.JSONDecodeError:
                pass

            except Exception as e:
                if self._on_error_cb:
                    self._on_error_cb(e)
                else:
                    print(f"[NasalMonitor] Error: {e}")

    # ─────────────────────────────────────────────
    # INTERNAL — auto-detect XIAO port
    # ─────────────────────────────────────────────

    def _autodetect_port(self) -> str:
        ports = serial.tools.list_ports.comports()
        for p in ports:
            if "usbmodem" in p.device.lower():
                print(f"[NasalMonitor] Auto-detected: {p.device}")
                return p.device
        for p in ports:
            if "USB" in p.description:
                print(f"[NasalMonitor] Auto-detected: {p.device}")
                return p.device
        raise RuntimeError(
            "[NasalMonitor] XIAO not found. "
            "Pass port= manually e.g. "
            "NasalMonitor(port='/dev/cu.usbmodem1101')"
        )