# Python API Reference

## Installation

    pip install -e .

---

## NasalMonitor

Main class. Connects to the XIAO over USB Serial, reads JSON packets, fires callbacks.

    from nasal_monitor import NasalMonitor

    monitor = NasalMonitor()

### Constructor Parameters

| Parameter | Default | Description |
|---|---|---|
| port | None | Serial port — auto-detected if None |
| baud | 115200 | Must match Arduino sketch |
| mic1_side | "left" | Nostril the yellow wire is on |
| mic2_side | "right" | Nostril the blue wire is on |
| live_detection | False | Enable real-time breath events (feedback only, never affects saved data) |
| sensitivity | 2.0 | Std deviations above baseline = breath (live_detection only) |
| min_breath_ms | 300 | Debounce — ignore events shorter than this (live_detection only) |
| target_hz | None | Downsample to this rate. None = full rate (~100–200 Hz raw ADC). e.g. target_hz=8 gives ~8 Hz peak-to-peak output, matching old firmware behaviour |

### Callbacks

    @monitor.on_reading          # every reading (raw ADC or downsampled p2p)
    def handle(r: RawReading): ...

    @monitor.on_breath           # breath state change (live_detection=True only)
    def handle(e: BreathEvent): ...

    @monitor.on_error            # serial or parse errors
    def handle(err: Exception): ...

### Methods

    monitor.start()                      # start background thread
    monitor.start_blocking()             # start and block until Ctrl+C
    monitor.stop()                       # clean shutdown
    monitor.board_to_host_time(ms)       # convert board millis() to Unix time
    monitor.current_thresholds          # adaptive thresholds dict (live_detection only)
    monitor.dropped_packets             # total dropped packets this session

---

## Downsampler

Accumulates high-rate raw ADC readings and emits one peak-to-peak aggregated
`RawReading` per window. Use directly if you need more control than `target_hz`.

    from nasal_monitor import Downsampler

    ds = Downsampler(hz=8.0)

    reading = ds.push(raw_reading)  # returns RawReading or None
    if reading:
        # reading.mic1 = peak-to-peak over the window
        process(reading)

---

## BreathDetector

Adaptive real-time breath classifier. Normally used via `NasalMonitor(live_detection=True)`.
Can also be instantiated directly for custom pipelines.

    from nasal_monitor import BreathDetector

    detector = BreathDetector(sensitivity=2.0, min_breath_ms=300)
    event = detector.process(reading)   # returns BreathEvent or None

---

## Data Classes

### RawReading

    @dataclass
    class RawReading:
        timestamp_ms:  int      # millis() from board
        host_time:     float    # Mac Unix timestamp
        seq:           int      # packet sequence number
        mic1:          int      # yellow mic — raw ADC (0–4095) or p2p if downsampled
        mic2:          int      # blue mic  — raw ADC (0–4095) or p2p if downsampled
        chip_temp_c:   float    # chip die temperature °C

### BreathEvent

    @dataclass
    class BreathEvent:
        host_time:     float
        board_ms:      int
        seq:           int
        side:          str      # "left" / "right" / "both" / "none"
        intensity:     float    # 0.0–1.0
        mic1_raw:      int
        mic2_raw:      int
        chip_temp_c:   float
        duration_ms:   float    # set when breath ends, None during

---

## CSV Output

Columns written by `examples/save_to_csv.py`:

| Column | Description |
|---|---|
| host_time | Mac Unix timestamp |
| board_ms | nRF millis() since boot |
| seq | Packet sequence number |
| mic1 | Yellow mic value |
| mic2 | Blue mic value |
| chip_temp_c | Chip temperature °C |

---

## Applying Thresholds in Analysis

Thresholds are never applied during recording. Apply them to saved CSV files:

    import json, pandas as pd

    df = pd.read_csv("session_1718123456.csv")

    with open("calibration/thresholds_P01_1718123456.json") as f:
        cfg = json.load(f)

    t1 = cfg["recommendations"]["mic1"]["recommended"]
    t2 = cfg["recommendations"]["mic2"]["recommended"]

    df["breath_left"]  = df["mic1"] >= t1
    df["breath_right"] = df["mic2"] >= t2

---

## Spectrum Analysis

    python analysis/spectrum.py calibration/raw_P01_1234567890.csv

Computes and plots the power spectral density of both mic channels using
Welch's method. Highlights the breathing frequency range (0.1–0.5 Hz).
Prints the dominant frequency in breaths/min.
