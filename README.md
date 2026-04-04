# Nasal Monitor

Synchronized nasal breathing and eye gaze monitor for research.
Records raw sensor data at full fidelity — all analysis decisions happen post-hoc.

---

## Hardware

| Component | Details |
|---|---|
| Board | Seeed Studio XIAO nRF52840 Plus |
| Mic 1 | Analog capacitive mic — Yellow wire → A0 (D0) |
| Mic 2 | Analog capacitive mic — Blue wire → A1 (D1) |
| Eye tracker | Tobii Pro Glasses 2 |
| Power | USB cable (development) or 3.7V LiPo JST 1.25mm (wearable) |

---

## Installation

    pip install -e .

---

## Project Structure

    nasal_monitor/
    ├── nasal_monitor/                  ← Python library
    │   ├── __init__.py                 ← public API
    │   ├── reader.py                   ← XIAO serial reader (raw data)
    │   ├── detector.py                 ← optional real-time breath detector
    │   ├── models.py                   ← data classes (RawReading, GazeData, etc.)
    │   ├── tobii_reader.py             ← Tobii Pro Glasses 2 gaze reader
    │   └── synchronizer.py             ← timestamp-based stream merger
    │
    ├── examples/                       ← session recording scripts
    │   ├── print_data.py               ← print raw readings to terminal
    │   ├── print_data_live.py          ← print with optional live detection
    │   ├── live_plot.py                ← real-time scrolling plot (raw signal)
    │   ├── save_to_csv.py              ← record full session to CSV
    │   └── gaze_breath.py             ← synchronized Tobii + XIAO session
    │
    ├── analysis/                       ← run separately, never affects recording
    │   └── threshold_server.py         ← guided calibration UI (Chrome app)
    │
    ├── calibration/                    ← auto-created by threshold_server.py
    │   ├── raw_P01_TIMESTAMP.csv       ← raw calibration data per participant
    │   └── thresholds_P01_TIMESTAMP.json ← threshold recommendations
    │
    ├── setup.py
    └── requirements.txt

---

## Data Philosophy

**Collect everything. Decide nothing during acquisition. Analyse later.**

    Acquisition layer:
      Arduino sketch  → raw sensor values, no classification
      Python library  → saves all raw data, no filtering

    Analysis layer (separate, run after recording):
      threshold_server.py → finds per-participant thresholds
      Your analysis scripts → apply thresholds to saved CSV

This means your raw CSV files are always intact and can be
re-analysed with different parameters at any time.

---

## Arduino Sketch

Located in the Arduino IDE project `XIAO_SensorReader`.

Output format — one JSON line per reading at ~8 Hz:

    {"t":37473,"seq":285,"m1":78,"m2":42,"temp":124}

| Field | Meaning |
|---|---|
| t | millis() — ms since board boot |
| seq | packet counter — detects dropped packets |
| m1 | mic1 peak-to-peak volume — yellow wire (0–4095) |
| m2 | mic2 peak-to-peak volume — blue wire (0–4095) |
| temp | chip die temperature raw (divide by 4 = °C) |

Upload method: double-press RESET → LED pulses → upload in Arduino IDE.

---

## Connecting Hardware

### XIAO nRF52840 Plus

Plug into Mac via USB-C. Port is auto-detected by the Python library.

### Tobii Pro Glasses 2

1. Power on the Recording Unit
2. On Mac — join the Tobii WiFi network (named `TobiiProGlasses2_XXXXXXXX`)
3. Find the IP address:

        python -c "from nasal_monitor import TobiiReader; TobiiReader.discover()"

4. Or check `192.168.71.50` (most common default)

Note: when connected to Tobii WiFi your Mac has no internet — this is normal.

---

## Running Examples

    # Raw readings in terminal (no Tobii needed)
    python examples/print_data.py

    # Raw readings with optional live breath detection visible
    python examples/print_data_live.py

    # Live scrolling plot of raw mic signal
    python examples/live_plot.py

    # Save full session to CSV
    python examples/save_to_csv.py

    # Synchronized Tobii + XIAO session (requires Tobii WiFi)
    python examples/gaze_breath.py

---

## Threshold Calibration Tool

Run before a study session to find per-participant signal thresholds.

    python analysis/threshold_server.py

Chrome opens automatically at `http://localhost:5500`.

**Workflow:**

1. Enter participant ID and optional notes
2. Overview screen shows all 8 scenarios
3. For each scenario:
   - Get Ready screen shows instructions
   - Researcher or participant presses **Space** or clicks **I'm Ready**
   - Circular countdown runs
   - 5-second rest between scenarios
4. Results screen shows threshold recommendations
5. Two files saved automatically to `calibration/`

**Scenarios recorded:**

| Scenario | Duration | Purpose |
|---|---|---|
| Baseline | 30s | Normal resting breathing — noise floor |
| Mouth only | 20s | True noise floor (no nasal signal) |
| Left nostril | 20s | Left mic signal level |
| Right nostril | 20s | Right mic signal level |
| Deep breathing | 20s | Upper signal range |
| Shallow breathing | 20s | Lower breath signal |
| Talking | 20s | Speech artefact characterisation |
| Head movement | 20s | Motion artefact characterisation |

**Output files:**

    calibration/raw_P01_1718123456.csv          ← full raw data, all scenarios
    calibration/thresholds_P01_1718123456.json  ← threshold recommendations

**Using thresholds in analysis:**

    import json, pandas as pd

    df = pd.read_csv("session_1718123456.csv")

    with open("calibration/thresholds_P01_1718123456.json") as f:
        config = json.load(f)

    t1 = config["recommendations"]["mic1"]["recommended"]
    t2 = config["recommendations"]["mic2"]["recommended"]

    df["breath_left"]  = df["mic1"] >= t1
    df["breath_right"] = df["mic2"] >= t2

---

## CSV Output Format

### Breathing only (`save_to_csv.py`)

| Column | Type | Description |
|---|---|---|
| host_time | float | Mac Unix timestamp |
| board_ms | int | nRF millis() since boot |
| seq | int | Packet sequence number |
| mic1 | int | Yellow mic raw (0–4095) |
| mic2 | int | Blue mic raw (0–4095) |
| chip_temp_c | float | Chip temperature °C |

### Synchronized session (`gaze_breath.py`)

All breathing columns above, plus:

| Column | Type | Description |
|---|---|---|
| gaze_x | float | 0.0–1.0 (left→right), -1 if invalid |
| gaze_y | float | 0.0–1.0 (top→bottom), -1 if invalid |
| pupil_left | float | mm diameter, -1 if invalid |
| pupil_right | float | mm diameter, -1 if invalid |
| gaze_valid | bool | False if Tobii lost the eye |

---

## Python Library API

    from nasal_monitor import NasalMonitor

    # Raw mode (default — always use for recording)
    monitor = NasalMonitor()

    # With optional live detection for real-time feedback only
    monitor = NasalMonitor(
        live_detection = True,
        sensitivity    = 2.0,     # std deviations above baseline
        min_breath_ms  = 300,     # debounce — ignore events < 300ms
    )

    # Configure which nostril each mic is on
    monitor = NasalMonitor(mic1_side="left", mic2_side="right")

    @monitor.on_reading
    def handle_raw(r):
        print(r.mic1, r.mic2, r.chip_temp_c)

    @monitor.on_breath          # only fires if live_detection=True
    def handle_breath(event):
        print(event.side, event.intensity)

    monitor.start_blocking()    # blocks until Ctrl+C

---

## Troubleshooting

| Problem | Fix |
|---|---|
| XIAO not found | Check USB cable, try unplugging and replugging |
| Serial Monitor blank | Ensure `delay(3000)` is in sketch setup |
| Upload fails | Double-press RESET button → LED pulses → upload |
| `AR_INTERNAL_2_4` error | Use `AR_INTERNAL2V4` (mbed package name) |
| Tobii not found | Check Mac is connected to Tobii WiFi |
| live_plot.py numpy error | Run in `venv_academia_py310` environment |
| Dropped packets warning | Normal for brief USB interruptions — check seq gaps in CSV |

---

## Synchronization Notes

The library uses a **time anchor** established on the first packet to convert
board timestamps (`millis()`) to real-world Unix time. This enables precise
alignment between XIAO breathing data and Tobii gaze data.

    anchor established at first packet:
      board_ms  = 3001       (millis since boot)
      host_time = 1718123456.234  (Mac Unix time)

    any board_ms can then be converted:
      real_time = host_time_anchor + (board_ms - anchor_board_ms) / 1000

The `seq` field in every packet lets you detect dropped packets during
post-hoc analysis — a gap in sequence numbers means data was lost.

---

## Dependencies

    pyserial>=3.5
    matplotlib
    tobiiglassesctrl
    flask
    flask-socketio