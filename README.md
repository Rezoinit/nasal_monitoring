# nasal_monitoring

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

Signal: ~8 Hz, 0–4095 ADC, JSON packets `{"t": ms, "seq": n, "m1": val, "m2": val}`.

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
python examples/live_plot.py         # real-time dual-channel plot
python examples/save_to_csv.py       # record a session to CSV
```

To run the threshold calibration web UI:
```bash
python analysis/threshold_server.py  # opens at http://localhost:5500
```

Or open `docs/index.html` directly in Chrome via Web Serial API.

---

## Library API

```python
from nasal_monitor import NasalMonitor, BreathDetector, RawReading, BreathEvent

monitor = NasalMonitor(port="/dev/tty.usbmodem...")
monitor.start()

detector = BreathDetector()
for reading in monitor.stream():          # RawReading(t, seq, m1, m2)
    events = detector.update(reading)     # list of BreathEvent
```

Key classes:

| Class | Description |
|---|---|
| `NasalMonitor` | Serial reader — yields `RawReading` objects |
| `BreathDetector` | Adaptive threshold breath detection (mean + N×std) |
| `RawReading` | `t, seq, m1, m2` — raw ADC sample |
| `BreathEvent` | `t, channel, direction` — detected breath crossing |

---

## Repository Structure

```
nasal_monitor/          Python library
examples/               Usage scripts
analysis/               Threshold calibration server
docs/                   Web app (index.html) and documentation
```

Documentation: [Setup](docs/SETUP.md) · [Arduino](docs/ARDUINO.md) · [API](docs/PYTHON_API.md) · [Calibration](docs/CALIBRATION.md)

---

## Related Repos

- [norad_response](https://github.com/rezoinit/norad_response) — combines this library with Tobii Pro Glasses 2 for LC-NE research
- [sleep_monitor](https://github.com/rezoinit/sleep_monitor) — overnight sleep breathing analysis built on this library

---

## License

MIT
