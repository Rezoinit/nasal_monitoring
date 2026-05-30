# nasal_monitor/session_recorder.py
# ─────────────────────────────────────────────────
# Robust raw-data recorder for study sessions.
#
# Designed to be imported by *other* repos that pair this nasal sensor
# with additional sensors.  All raw readings are written to disk
# immediately (no buffering) so data is preserved even if the process
# is interrupted.
#
# Output per session:
#   <output_dir>/<study>_<participant>_<timestamp>/
#       raw_data.csv        — every reading, every field
#       session_manifest.json — metadata + end-of-session statistics
# ─────────────────────────────────────────────────

from __future__ import annotations

import csv
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .models import RawReading


@dataclass
class SessionMeta:
    """Metadata that travels alongside every recorded session."""
    participant_id: str
    study_name: str
    scenario: str
    sensor_info: Dict[str, Any]        # free-form: board, firmware, mic positions, …
    extra: Dict[str, Any]              # caller-supplied key-value pairs
    start_time: float = 0.0            # Unix timestamp, filled by SessionRecorder
    output_dir: str = ""               # filled by SessionRecorder


class SessionRecorder:
    """
    Write every RawReading to CSV the moment it arrives, and save a JSON
    manifest when the session ends.

    Typical usage (nasal-only study)
    ---------------------------------
    ::

        from nasal_monitor import NasalMonitor, SessionRecorder

        rec = SessionRecorder(
            participant_id = "P01",
            study_name     = "resting_state",
            scenario       = "eyes_open",
            sensor_info    = {"board": "xiao_nrf52840", "mic1_side": "left"},
            output_dir     = "recordings",
        )

        monitor = NasalMonitor()

        @monitor.on_reading
        def on_reading(r):
            rec.record(r)

        rec.start()
        monitor.start_blocking()
        rec.stop()

    Multi-sensor study (import from another repo)
    -----------------------------------------------
    ::

        # other_repo/run_study.py
        from nasal_monitor import SessionRecorder, RawReading
        from nasal_monitor import NasalMonitor

        rec = SessionRecorder(
            participant_id = "S05",
            study_name     = "dual_sensor_pilot",
            scenario       = "treadmill_3kph",
            sensor_info    = {
                "nasal_board": "xiao_nrf52840",
                "other_sensor": "polar_h10",
            },
            output_dir     = "data/raw",
            extra          = {"speed_kmh": 3, "incline_deg": 0},
        )

        rec.start()
        # … connect other sensors, record nasal readings via rec.record(r)
        rec.stop()
    """

    CSV_HEADER = [
        "host_time",    # Unix timestamp (float, seconds)
        "board_ms",     # nRF millis() since boot
        "seq",          # packet sequence number
        "mic1",         # left nostril amplitude (0–4095 raw ADC)
        "mic2",         # right nostril amplitude (0–4095 raw ADC)
        "chip_temp_c",  # chip die temperature in °C
        "scenario",     # echoed from session metadata for easy CSV filtering
    ]

    def __init__(
        self,
        participant_id: str,
        study_name: str,
        scenario: str = "default",
        sensor_info: Optional[Dict[str, Any]] = None,
        output_dir: str = "recordings",
        extra: Optional[Dict[str, Any]] = None,
        print_progress: bool = True,
        flush_every_n: int = 1,
    ):
        """
        Parameters
        ----------
        participant_id  : unique participant identifier (e.g. ``"P01"``)
        study_name      : short name for the study/protocol (e.g. ``"resting_state"``)
        scenario        : condition label within the study (e.g. ``"eyes_open"``)
        sensor_info     : free-form dict describing hardware (board, firmware,
                          mic positions, etc.)
        output_dir      : root directory where session folders are created
        extra           : any additional metadata you want in the manifest
        print_progress  : print a one-liner per recorded packet  (default True)
        flush_every_n   : flush the CSV file every N packets  (default 1 = always;
                          increase to e.g. 10 for high-rate sensors)
        """
        self.meta = SessionMeta(
            participant_id = participant_id,
            study_name     = study_name,
            scenario       = scenario,
            sensor_info    = sensor_info or {},
            extra          = extra or {},
        )
        self._output_root   = output_dir
        self._print         = print_progress
        self._flush_every_n = flush_every_n

        self._session_dir:  Optional[str]              = None
        self._csv_path:     Optional[str]              = None
        self._manifest_path: Optional[str]             = None
        self._file:         Optional[Any]              = None
        self._writer:       Optional[csv.writer]       = None

        self._n_records:    int   = 0
        self._n_dropped:    int   = 0
        self._last_seq:     int   = -1
        self._start_time:   float = 0.0
        self._started:      bool  = False

    # ─────────────────────────────────────────────
    # PUBLIC
    # ─────────────────────────────────────────────

    def start(self) -> str:
        """
        Open the output files and begin recording.

        Returns the path to the session directory.
        """
        if self._started:
            raise RuntimeError("SessionRecorder.start() called twice.")

        ts = int(time.time())
        folder_name = (
            f"{self.meta.study_name}_{self.meta.participant_id}_{ts}"
        )
        self._session_dir   = os.path.join(self._output_root, folder_name)
        os.makedirs(self._session_dir, exist_ok=True)

        self._csv_path      = os.path.join(self._session_dir, "raw_data.csv")
        self._manifest_path = os.path.join(self._session_dir, "session_manifest.json")

        self._file   = open(self._csv_path, "w", newline="")
        self._writer = csv.writer(self._file)
        self._writer.writerow(self.CSV_HEADER)

        self._start_time       = time.time()
        self.meta.start_time   = self._start_time
        self.meta.output_dir   = self._session_dir
        self._started          = True

        self._write_manifest(complete=False)

        if self._print:
            print(f"[SessionRecorder] Started  → {self._session_dir}")
        return self._session_dir

    def record(self, reading: RawReading) -> None:
        """
        Write one reading to the CSV.  Call this from your on_reading callback.

        Thread-safe for a single writer thread (NasalMonitor background thread).
        """
        if not self._started:
            raise RuntimeError("Call SessionRecorder.start() before record().")

        if self._last_seq >= 0:
            gap = reading.seq - self._last_seq
            if gap > 1:
                self._n_dropped += gap - 1
        self._last_seq = reading.seq

        self._writer.writerow([
            f"{reading.host_time:.4f}",
            reading.timestamp_ms,
            reading.seq,
            reading.mic1,
            reading.mic2,
            f"{reading.chip_temp_c:.2f}",
            self.meta.scenario,
        ])

        self._n_records += 1
        if self._n_records % self._flush_every_n == 0:
            self._file.flush()

        if self._print:
            print(
                f"  seq={reading.seq:6d}  "
                f"mic1={reading.mic1:4d}  "
                f"mic2={reading.mic2:4d}  "
                f"temp={reading.chip_temp_c:.1f}°C"
            )

    def stop(self) -> Dict[str, Any]:
        """
        Flush, close the CSV, and write the final session manifest.

        Returns the manifest dict.
        """
        if not self._started:
            raise RuntimeError("SessionRecorder was never started.")

        self._file.flush()
        self._file.close()
        manifest = self._write_manifest(complete=True)

        if self._print:
            print(
                f"[SessionRecorder] Stopped  → {self._n_records} samples, "
                f"{manifest['duration_s']:.1f} s, "
                f"{manifest['estimated_fs_hz']:.1f} Hz, "
                f"{self._n_dropped} dropped packets"
            )
            print(f"[SessionRecorder] Manifest → {self._manifest_path}")
        return manifest

    # ─────────────────────────────────────────────
    # PROPERTIES
    # ─────────────────────────────────────────────

    @property
    def n_records(self) -> int:
        return self._n_records

    @property
    def n_dropped(self) -> int:
        return self._n_dropped

    @property
    def session_dir(self) -> Optional[str]:
        return self._session_dir

    @property
    def csv_path(self) -> Optional[str]:
        return self._csv_path

    # ─────────────────────────────────────────────
    # INTERNAL
    # ─────────────────────────────────────────────

    def _write_manifest(self, complete: bool) -> Dict[str, Any]:
        now = time.time()
        duration = now - self._start_time if self._start_time else 0.0
        fs_est = self._n_records / duration if duration > 0 else 0.0

        manifest: Dict[str, Any] = {
            "participant_id":    self.meta.participant_id,
            "study_name":        self.meta.study_name,
            "scenario":          self.meta.scenario,
            "sensor_info":       self.meta.sensor_info,
            "extra":             self.meta.extra,
            "start_time_unix":   self.meta.start_time,
            "start_time_iso":    _iso(self.meta.start_time),
            "end_time_unix":     now if complete else None,
            "end_time_iso":      _iso(now) if complete else None,
            "duration_s":        round(duration, 2),
            "n_samples":         self._n_records,
            "n_dropped_packets": self._n_dropped,
            "estimated_fs_hz":   round(fs_est, 2),
            "csv_path":          self._csv_path,
            "complete":          complete,
        }

        if self._manifest_path:
            with open(self._manifest_path, "w") as f:
                json.dump(manifest, f, indent=2)

        return manifest


def _iso(unix_ts: float) -> str:
    import datetime
    return datetime.datetime.utcfromtimestamp(unix_ts).strftime("%Y-%m-%dT%H:%M:%SZ")
