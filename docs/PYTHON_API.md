# Python API Reference

## Installation

    pip install -e .

---

## NasalMonitor

Main class for reading raw data from the XIAO over USB Serial.

    from nasal_monitor import NasalMonitor

    monitor = NasalMonitor()

### Constructor Parameters

| Parameter | Default | Description |
|---|---|---|
| port | None | Serial port — auto-detected if None |
| baud | 115200 | Must match Arduino sketch |
| mic1_side | "left" | Nostril yellow wire is on |
| mic2_side | "right" | Nostril blue wire is on |
| live_detection | False | Enable real-time breath events (feedback only) |
| sensitivity | 2.0 | Adaptive threshold sensitivity (std deviations) |
| min_breath_ms | 300 | Debounce — ignore events shorter than this |

### Callbacks

    @monitor.on_reading          # every raw reading (~8Hz)
    def handle(r: RawReading): ...

    @monitor.on_breath           # breath state changes (live_detection=True only)
    def handle(e: BreathEvent): ...

    @monitor.on_error            # serial or parse errors
    def handle(err: Exception): ...

### Methods

    monitor.start()              # start in background thread
    monitor.start_blocking()     # start and block until Ctrl+C
    monitor.stop()               # clean shutdown
    monitor.board_to_host_time(board_ms)  # convert board time to Unix time
    monitor.current_thresholds   # adaptive thresholds (if live_detection=True)
    monitor.dropped_packets      # total dropped packets this session

---

## Data Classes

### RawReading

    @dataclass
    class RawReading:
        timestamp_ms:  int      # millis() from board
        host_time:     float    # Mac Unix timestamp
        seq:           int      # packet sequence number
        mic1:          int      # yellow mic (0–4095)
        mic2:          int      # blue mic   (0–4095)
        chip_temp_c:   float    # chip temperature °C

### GazeData

    @dataclass
    class GazeData:
        host_time:     float    # Mac Unix timestamp
        gaze_x:        float    # 0.0 (left) to 1.0 (right)
        gaze_y:        float    # 0.0 (top)  to 1.0 (bottom)
        pupil_left:    float    # mm, -1.0 if invalid
        pupil_right:   float    # mm, -1.0 if invalid
        valid:         bool

### SyncedEvent

    @dataclass
    class SyncedEvent:
        host_time:     float
        gaze_x:        float
        gaze_y:        float
        pupil_left:    float
        pupil_right:   float
        gaze_valid:    bool
        mic1_raw:      int
        mic2_raw:      int
        seq:           int
        board_ms:      int
        chip_temp_c:   float

---

## TobiiReader

    from nasal_monitor import TobiiReader

    address = TobiiReader.discover()        # auto-find on network
    tobii   = TobiiReader("192.168.71.50") # or specify IP

    @tobii.on_gaze
    def handle(g: GazeData): ...

    tobii.start()
    tobii.stop()

---

## Synchronizer

Merges XIAO and Tobii streams by timestamp within a 100ms window.

    from nasal_monitor import NasalMonitor, TobiiReader, Synchronizer

    xiao  = NasalMonitor()
    tobii = TobiiReader(address)
    sync  = Synchronizer(xiao, tobii)

    @sync.on_event
    def handle(e: SyncedEvent): ...

    sync.start_blocking()

---

## CSV Output

### Breathing only

| Column | Description |
|---|---|
| host_time | Mac Unix timestamp |
| board_ms | nRF millis() since boot |
| seq | Packet sequence number |
| mic1 | Yellow mic raw (0–4095) |
| mic2 | Blue mic raw (0–4095) |
| chip_temp_c | Chip temperature °C |

### Synchronized session (adds)

| Column | Description |
|---|---|
| gaze_x | 0.0–1.0, -1 if invalid |
| gaze_y | 0.0–1.0, -1 if invalid |
| pupil_left | mm, -1 if invalid |
| pupil_right | mm, -1 if invalid |
| gaze_valid | True / False |

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