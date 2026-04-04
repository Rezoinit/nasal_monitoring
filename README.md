# Nasal Breathing Monitoring

A lightweight research tool for synchronized nasal breathing and eye gaze data collection. Built for wearable use with the Seeed Studio XIAO nRF52840 and Tobii Pro Glasses 2.

---

## Overview

Nasal Monitor captures bilateral nasal airflow signals from two analog microphones and synchronizes them with eye gaze data from Tobii Pro Glasses 2. All data is recorded at full fidelity with no on-device filtering — analysis decisions are made post-hoc.

The system is designed around three principles:

- **Collect everything** — raw sensor values, board timestamps, and packet sequence numbers are preserved at every stage
- **Decide later** — no thresholds or classifications are applied during recording
- **Synchronize precisely** — a time anchor aligns board and host clocks to millisecond accuracy

---

## Play with the sensor

Connect your XIAO nRF52840 Plus and open the web app in Chrome:

<a href="https://rezoinit.github.io/nasal_monitoring/">
  <img src="https://img.shields.io/badge/Calibrate-1D6BF3?style=for-the-badge&logoColor=white" alt="Calibrate" height="40"/>
</a>

<br><br>

The app guides you through a short calibration and then displays live breathing data in real time.

> Requires Google Chrome and a XIAO nRF52840 Plus with microphones attached.

---

## Hardware

| Component | Role |
|---|---|
| Seeed Studio XIAO nRF52840 Plus | Microcontroller — reads microphones, streams JSON over USB |
| 2× Analog capacitive microphones | Left and right nasal airflow sensors |
| Tobii Pro Glasses 2 | Eye gaze and pupillometry |
| 3.7V LiPo battery (JST 1.25mm) | Optional — for wireless wearable deployment |

---

## System Architecture

    XIAO nRF52840  ──USB──▶  Python library  ──▶  CSV (raw)
    Tobii Glasses  ──WiFi──▶  Synchronizer   ──▶  CSV (synced)
                                              ──▶  Live plot

The Python library runs two independent threads — one for serial data from the XIAO, one for gaze data from Tobii — and merges them by timestamp into a single synchronized event stream.

---

## Repository Structure

    nasal_monitor/
    ├── nasal_monitor/          Python library
    ├── examples/               Recording and visualization scripts
    ├── analysis/               Calibration and threshold tools
    └── docs/                   Web app and detailed documentation

## Documentation

- [Hardware Setup](docs/SETUP.md)
- [Arduino Sketch](docs/ARDUINO.md)
- [Python API Reference](docs/PYTHON_API.md)
- [Calibration Tool](docs/CALIBRATION.md)

---

## Quick Start

    pip install -e .
    python examples/print_data.py      # raw readings
    python examples/live_plot.py       # real-time plot
    python examples/save_to_csv.py     # record session

---

## Status

Active development. Tobii integration complete. BLE wireless mode planned for next phase.

---

## Citation

If you use this tool in your research, please cite:

    [Your Name] (2025). Nasal Monitor: Synchronized nasal breathing
    and eye gaze acquisition tool. GitHub.
    https://github.com/YOUR_USERNAME/nasal_monitor

---

## License

MIT