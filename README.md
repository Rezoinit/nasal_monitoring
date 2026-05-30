# Nasal Airflow Monitoring

Bilateral nasal airflow monitoring using the Seeed Studio XIAO nRF52840 and two analog MEMS microphones. Streams raw ADC signals over USB serial, records full sessions to disk, and provides a peer-reviewed analysis library for offline signal processing.

Designed to run standalone or as a sensor module inside a larger multi-sensor study repo.

---

## Try it in the browser

Connect your XIAO nRF52840 Plus and open the web app in Chrome:

<p align="center">
  <a href="https://rezoinit.github.io/nasal_monitoring/">
    <img src="docs/calibrate-btn.svg" alt="Open Web App" height="72"/>
  </a>
</p>

The app connects to the device via Web Serial, runs a short calibration, and displays live bilateral breathing data in real time.

> Requires Google Chrome and a XIAO nRF52840 Plus with microphones attached.

---

## Hardware

| Component | Role |
|---|---|
| Seeed Studio XIAO nRF52840 Plus | Reads microphones, streams JSON over USB at 115200 baud |
| 2× Analog capacitive microphones | Left (MIC1 / yellow wire) and right (MIC2 / blue wire) nasal airflow |
| 3.7V LiPo (JST 1.25mm) | Optional — untethered wearable use |

Signal: raw ADC at ~150 Hz, 0–4095, JSON packets `{"t": ms, "seq": n, "m1": val, "m2": val, "temp": val}`.

---

## Install

```bash
pip install -e .
```

Requires: `pyserial`, `matplotlib`, `numpy`, `scipy`, `pandas`

---

## Quick Start

```bash
python examples/print_data.py        # print raw readings to terminal
python examples/live_plot.py         # real-time plot at 8 Hz (peak-to-peak)
python examples/save_to_csv.py       # record a session to CSV
```

Full analysis dashboard (all functions live):
```bash
python live_plot.py
python live_plot.py --port /dev/cu.usbmodem1101 --hz 8 --window 60
```

Threshold calibration web UI:
```bash
python calibration/threshold_server.py   # opens at http://localhost:5500
```

Web demo locally:
```bash
cd docs && python -m http.server 8000    # open http://localhost:8000 in Chrome
```

---

## Recording a Study Session

`SessionRecorder` writes every raw reading to CSV the moment it arrives (no buffering) and saves a JSON manifest when the session ends. Use it for any study — nasal-only or multi-sensor.

```python
from nasal_monitor import NasalMonitor, SessionRecorder

rec = SessionRecorder(
    participant_id = "P01",
    study_name     = "resting_state",
    scenario       = "eyes_open",
    sensor_info    = {"board": "xiao_nrf52840", "mic1_side": "left"},
    output_dir     = "recordings",
)

monitor = NasalMonitor(target_hz=8)

@monitor.on_reading
def on_reading(r):
    rec.record(r)

rec.start()
monitor.start_blocking()   # Ctrl+C to stop
rec.stop()
```

Output written to `recordings/<study>_<participant>_<timestamp>/`:
- `raw_data.csv` — every reading, every field
- `session_manifest.json` — metadata, duration, sample count, estimated Hz, dropped packets

---

## Using This Package in Another Repo (Multi-Sensor Studies)

Install this package into any other Python environment:

```bash
pip install git+https://github.com/rezoinit/nasal_monitoring.git
```

Then import `SessionRecorder` and `NasalMonitor` directly alongside your other sensors:

```python
from nasal_monitor import NasalMonitor, SessionRecorder, RawReading

rec = SessionRecorder(
    participant_id = "S05",
    study_name     = "dual_sensor_pilot",
    scenario       = "treadmill_3kph",
    sensor_info    = {
        "nasal_board":  "xiao_nrf52840",
        "other_sensor": "polar_h10",
    },
    output_dir = "data/raw",
    extra      = {"speed_kmh": 3, "incline_deg": 0},
)

monitor = NasalMonitor(target_hz=8)

@monitor.on_reading
def on_reading(r):
    rec.record(r)          # nasal data → session CSV
    your_other_sensor.sync(r.host_time)   # align timestamps

rec.start()
monitor.start()
# … start your other sensors here using the same host clock
rec.stop()
```

`host_time` on every `RawReading` is a Unix timestamp from the host machine, so it aligns directly with timestamps from any other sensor you record on the same computer.

---

## Analysis Library

Post-hoc analysis functions in `analysis/`. Every function exposes all key parameters and cites the peer-reviewed source that defines the method.

```python
from analysis import analyse_recording
import numpy as np, pandas as pd

df = pd.read_csv("recordings/.../raw_data.csv")
result = analyse_recording(df["mic1"].values, df["mic2"].values, fs=8.0)

print(result["rate"]["psd_bpm"])          # breathing rate (Welch PSD)
print(result["nasal"]["dominance"])        # left / right / balanced
print(result["pattern"]["pattern"])        # normal / bradypnea / tachypnea
```

| Function | Method | Reference |
|---|---|---|
| `bandpass_filter` | Butterworth bandpass | Butterworth 1930 |
| `detect_breath_peaks` | AMPD or scipy find_peaks | Scholkmann et al. 2012 |
| `estimate_rate_psd` | Welch PSD | Welch 1967 |
| `estimate_rate_peaks` | Peak interval mean | — |
| `estimate_rate_autocorr` | Autocorrelation | — |
| `nasal_asymmetry_index` | NAI = (m1−m2)/(m1+m2)×100 | Eccles 1996 |
| `bilateral_coherence` | Magnitude-squared coherence | Carter 1987 |
| `breathing_variability` | SDBB, RMSSD, CV, pBB50 | Task Force ESC 1996 |
| `instantaneous_rate` | Interpolated peak intervals | — |
| `sample_entropy` | SampEn | Richman & Moorman 2000 |
| `detect_artifacts` | Motion + speech heuristics | — |
| `classify_breathing_pattern` | Rate thresholds | — |
| `analyse_recording` | Full pipeline wrapper | — |

---

## Library API

```python
from nasal_monitor import NasalMonitor

monitor = NasalMonitor(target_hz=8)   # downsample to 8 Hz peak-to-peak

@monitor.on_reading
def handle(r):
    print(r.mic1, r.mic2)

monitor.start_blocking()
```

Key classes:

| Class | Description |
|---|---|
| `NasalMonitor` | Serial reader — fires `on_reading` / `on_breath` callbacks |
| `BreathDetector` | Adaptive real-time classifier (mean + N×std above baseline) |
| `Downsampler` | Accumulates raw ADC, emits peak-to-peak per time window |
| `RawReading` | `timestamp_ms, host_time, seq, mic1, mic2, chip_temp_c` |
| `BreathEvent` | `host_time, side, intensity, duration_ms, …` |
| `SessionRecorder` | Writes raw readings to CSV + JSON manifest per session |
| `SessionMeta` | Metadata dataclass (participant, study, scenario, sensor info) |

---

## Repository Structure

```
nasal_monitor/          Python library (monitor, models, session recorder)
analysis/               Post-hoc analysis library (peer-reviewed methods)
examples/               Minimal usage scripts
calibration/            Threshold calibration server and output files
docs/                   Web app (index.html) and documentation
arduino/                Arduino sketch for the XIAO board
live_plot.py            Full real-time analysis dashboard
```
Parts of this codebase were developed with Claude.

Documentation: [Setup](docs/SETUP.md) · [Arduino](docs/ARDUINO.md) · [API](docs/API.md) · [Calibration](docs/CALIBRATION.md)


---

## License

MIT
