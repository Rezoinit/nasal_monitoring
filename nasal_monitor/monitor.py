# nasal_monitor/monitor.py
# ─────────────────────────────────────────────────
# All runtime tools in one place:
#
#   Downsampler     — accumulates high-rate raw readings,
#                     emits one peak-to-peak aggregate per window
#
#   BreathDetector  — adaptive real-time breath classifier
#                     (optional, for live feedback only)
#
#   NasalMonitor    — connects to XIAO over USB Serial,
#                     reads JSON, fires callbacks
# ─────────────────────────────────────────────────

import json
import time
import threading
import collections
import serial
import serial.tools.list_ports
from typing import Callable, List, Optional

from .models import RawReading, BreathEvent


# ═════════════════════════════════════════════════
# DOWNSAMPLER
# ═════════════════════════════════════════════════

class Downsampler:
    """
    Accumulates high-rate raw ADC readings and emits one aggregated
    RawReading per 1/hz seconds.

    mic1/mic2 : peak-to-peak (max - min) over the window,
                preserving the same meaning as the old fixed-rate firmware.
    chip_temp : mean over the window.
    """

    def __init__(self, hz: float = 8.0):
        if hz <= 0:
            raise ValueError("hz must be positive")
        self._window_s = 1.0 / hz
        self._buffer: List[RawReading] = []
        self._window_start: Optional[float] = None

    def push(self, reading: RawReading) -> Optional[RawReading]:
        """
        Add a reading. Returns an aggregated RawReading when the window
        closes, None otherwise.
        """
        if self._window_start is None:
            self._window_start = reading.host_time

        self._buffer.append(reading)

        if reading.host_time - self._window_start >= self._window_s:
            result = self._aggregate()
            self._buffer = []
            self._window_start = reading.host_time
            return result

        return None

    def _aggregate(self) -> RawReading:
        buf = self._buffer
        return RawReading(
            timestamp_ms = buf[-1].timestamp_ms,
            host_time    = buf[-1].host_time,
            seq          = buf[-1].seq,
            mic1         = max(r.mic1 for r in buf) - min(r.mic1 for r in buf),
            mic2         = max(r.mic2 for r in buf) - min(r.mic2 for r in buf),
            chip_temp_c  = sum(r.chip_temp_c for r in buf) / len(buf),
        )


# ═════════════════════════════════════════════════
# BREATH DETECTOR
# ═════════════════════════════════════════════════

class BreathDetector:
    """
    Real-time adaptive breath classifier.

    Used ONLY for live feedback (e.g. live plot, LED trigger).
    Never affects raw data or what gets saved to disk.

    Self-calibrates to each participant — no manual threshold tuning needed.
    """

    def __init__(
        self,
        mic1_side:     str   = "left",
        mic2_side:     str   = "right",
        window_size:   int   = 250,   # readings in baseline window (~30s at 8Hz)
        sensitivity:   float = 2.0,   # std deviations above baseline = breath
        min_breath_ms: float = 300,   # debounce — ignore events shorter than this
    ):
        self.mic1_side     = mic1_side
        self.mic2_side     = mic2_side
        self.sensitivity   = sensitivity
        self.min_breath_ms = min_breath_ms

        self._mic1_buf = collections.deque(maxlen=window_size)
        self._mic2_buf = collections.deque(maxlen=window_size)

        self._last_side:    str            = "none"
        self._breath_start: Optional[float] = None

    def _threshold(self, buf: collections.deque) -> float:
        if len(buf) < 30:
            return 80.0  # fallback until buffer fills (~4s)
        values = list(buf)
        mean   = sum(values) / len(values)
        var    = sum((x - mean) ** 2 for x in values) / len(values)
        std    = var ** 0.5
        return mean + (self.sensitivity * std)

    def process(self, reading: RawReading) -> Optional[BreathEvent]:
        """
        Feed one RawReading. Returns BreathEvent if breath state changed,
        None otherwise.
        """
        self._mic1_buf.append(reading.mic1)
        self._mic2_buf.append(reading.mic2)

        thresh1 = self._threshold(self._mic1_buf)
        thresh2 = self._threshold(self._mic2_buf)

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

        i1 = max(0.0, (reading.mic1 - thresh1) / thresh1)
        i2 = max(0.0, (reading.mic2 - thresh2) / thresh2)
        intensity = round(min(max(i1, i2), 1.0), 3)

        if current_side == self._last_side:
            return None

        if (current_side == "none"
                and self._last_side != "none"
                and self._breath_start is not None):
            duration = (reading.host_time - self._breath_start) * 1000
            if duration < self.min_breath_ms:
                self._last_side = current_side
                return None

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

        if current_side == "none" and self._breath_start is not None:
            event.duration_ms = (reading.host_time - self._breath_start) * 1000

        if current_side != "none":
            self._breath_start = reading.host_time

        self._last_side = current_side
        return event

    def current_thresholds(self) -> dict:
        return {
            "mic1_threshold": round(self._threshold(self._mic1_buf), 1),
            "mic2_threshold": round(self._threshold(self._mic2_buf), 1),
        }


# ═════════════════════════════════════════════════
# NASAL MONITOR
# ═════════════════════════════════════════════════

class NasalMonitor:
    """
    Connects to XIAO over USB Serial, reads JSON packets,
    and fires callbacks.

    Two strictly separate layers:

      Layer 1 — RAW DATA (always active)
        on_reading fires for every packet (or every downsampled window).
        This is your data — never filtered.

      Layer 2 — LIVE DETECTION (opt-in)
        Only active if live_detection=True.
        Used only for real-time feedback.
        Zero effect on raw data layer.
    """

    def __init__(
        self,
        port:           Optional[str]   = None,
        baud:           int             = 115200,
        mic1_side:      str             = "left",
        mic2_side:      str             = "right",
        live_detection: bool            = False,
        sensitivity:    float           = 2.0,
        min_breath_ms:  float           = 300,
        target_hz:      Optional[float] = None,
    ):
        """
        port           : serial port — auto-detected if None
        baud           : must match Arduino sketch (115200)
        mic1_side      : nostril the yellow wire is on
        mic2_side      : nostril the blue wire is on

        live_detection : set True for real-time breath events (feedback only)
                         has zero effect on raw data recording
        sensitivity    : std deviations above baseline = breath
                         (only used if live_detection=True)
        min_breath_ms  : debounce window in ms
                         (only used if live_detection=True)

        target_hz      : downsample Arduino output to this rate.
                         None = pass every raw packet through at full rate.
                         e.g. target_hz=8 → ~8 Hz output with peak-to-peak
                         amplitude per window, matching old firmware behaviour.
        """
        self.port = port or self._autodetect_port()
        self.baud = baud

        # ── Downsampler ───────────────────────────
        self._downsampler: Optional[Downsampler] = None
        if target_hz is not None:
            self._downsampler = Downsampler(hz=target_hz)

        # ── Live detector ─────────────────────────
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

        # ── Packet integrity ──────────────────────
        self._last_seq: int = 0
        self._dropped:  int = 0

        # ── Internal ──────────────────────────────
        self._serial:  Optional[serial.Serial]   = None
        self._thread:  Optional[threading.Thread] = None
        self._running: bool = False

    # ─────────────────────────────────────────────
    # DECORATORS
    # ─────────────────────────────────────────────

    def on_reading(self, fn: Callable) -> Callable:
        """Fires for every reading. Always active."""
        self._on_reading_cb = fn
        return fn

    def on_breath(self, fn: Callable) -> Callable:
        """Fires on breath state changes. Only active if live_detection=True."""
        self._on_breath_cb = fn
        return fn

    def on_error(self, fn: Callable) -> Callable:
        """Fires on serial or parse errors."""
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
        """Current adaptive thresholds. None if live_detection=False."""
        if self._detector:
            return self._detector.current_thresholds()
        return None

    def board_to_host_time(self, board_ms: int) -> Optional[float]:
        """Convert board millis() to Unix time. None until anchor established."""
        if self._anchor_host is None:
            return None
        return self._anchor_host + (board_ms - self._anchor_board) / 1000.0

    # ─────────────────────────────────────────────
    # START / STOP
    # ─────────────────────────────────────────────

    def start(self):
        print(f"[NasalMonitor] Connecting to {self.port}...")
        self._serial  = serial.Serial(self.port, self.baud, timeout=2)
        self._running = True
        self._thread  = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

        if self._downsampler:
            mode = f"full rate → downsampled to {1/self._downsampler._window_s:.1f} Hz"
        else:
            mode = "full rate (no downsampling)"
        if self._detector:
            mode += " + live detection (feedback only)"
        print(f"[NasalMonitor] Running — {mode}")

    def stop(self):
        self._running = False
        if self._serial and self._serial.is_open:
            self._serial.close()
        print(f"[NasalMonitor] Stopped. Dropped packets: {self._dropped}")

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

    def _read_loop(self):
        while self._running:
            try:
                raw_line = self._serial.readline().decode("utf-8").strip()
                if not raw_line:
                    continue

                data = json.loads(raw_line)

                if "status" in data:
                    print(f"[NasalMonitor] Board ready. boot_ms={data.get('boot_ms', '?')}")
                    continue

                host_now = time.time()
                reading  = RawReading(
                    timestamp_ms = data["t"],
                    host_time    = host_now,
                    seq          = data["seq"],
                    mic1         = data["m1"],
                    mic2         = data["m2"],
                    chip_temp_c  = data["temp"] / 4.0,
                )

                if self._anchor_host is None:
                    self._anchor_host  = host_now
                    self._anchor_board = reading.timestamp_ms
                    print(
                        f"[NasalMonitor] Time anchor set. "
                        f"board_ms={reading.timestamp_ms} host={host_now:.3f}"
                    )

                if self._last_seq > 0:
                    gap = reading.seq - self._last_seq
                    if gap > 1:
                        self._dropped += gap - 1
                        print(
                            f"[NasalMonitor] ⚠️  {gap-1} packet(s) dropped "
                            f"(seq {self._last_seq}→{reading.seq})"
                        )
                self._last_seq = reading.seq

                # ── DOWNSAMPLING LAYER ────────────
                if self._downsampler:
                    reading = self._downsampler.push(reading)
                    if reading is None:
                        continue

                # ── RAW DATA LAYER ────────────────
                if self._on_reading_cb:
                    self._on_reading_cb(reading)

                # ── LIVE DETECTION LAYER ──────────
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
            "Pass port= manually e.g. NasalMonitor(port='/dev/cu.usbmodem1101')"
        )
