# Nasal Airflow Monitoring

Standalone Python library for bilateral nasal airflow monitoring using the Seeed Studio XIAO nRF52840 and two analog MEMS microphones. Captures raw ADC signals over USB serial, detects breath events, and records to CSV.

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
| 2× Analog capacitive microphones | Left (MIC1) and right (MIC2) nasal airflow |
| 3.7V LiPo (JST 1.25mm) | Optional — untethered wearable use |

Signal: raw ADC at ~150 Hz, 0–4095, JSON packets `{"t": ms, "seq": n, "m1": val, "m2": val}`.

---

## Install

```bash
pip install -e .
```

Requires: `pyserial`, `matplotlib`

---

## Quick Start

```bash
python examples/print_data.py        # print raw readings to terminal
python examples/live_plot.py         # real-time plot at 8 Hz (peak-to-peak)
python examples/save_to_csv.py       # record a session to CSV
```

To run the threshold calibration web UI:
```bash
python calibration/threshold_server.py  # opens at http://localhost:5500
```

To use the web demo locally (Web Serial requires a served page, not file://):
```bash
cd docs && python -m http.server 8000   # then open http://localhost:8000 in Chrome
```

---

## Library API

```python
from nasal_monitor import NasalMonitor

monitor = NasalMonitor(target_hz=8)   # downsample to 8 Hz peak-to-peak

@monitor.on_reading
def handle(r):
    print(r.mic1, r.mic2)   # peak-to-peak amplitude per channel

monitor.start_blocking()
```

With live breath detection:

```python
monitor = NasalMonitor(live_detection=True, target_hz=8)

@monitor.on_breath
def handle(event):
    print(event.side, event.intensity)   # "left" / "right" / "both" / "none"

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

---

## Repository Structure

```
nasal_monitor/          Python library
examples/               Usage scripts
calibration/            Threshold calibration server and output files
analysis/               Post-hoc signal analysis tools
docs/                   Web app (index.html) and documentation
arduino/                Arduino sketch for the XIAO board
```

Documentation: [Setup](docs/SETUP.md) · [Arduino](docs/ARDUINO.md) · [API](docs/API.md) · [Calibration](docs/CALIBRATION.md)

---

## License

MIT
