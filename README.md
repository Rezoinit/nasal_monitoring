# Nasal Monitoring

Synchronized nasal breathing + eye gaze monitor for research.

## Hardware
- Seeed Studio XIAO nRF52840 Plus
- 2x analog capacitive microphones (Yellow → A0, Blue → A1)
- Tobii Pro Glasses 2

## Setup

### Install
```bash
pip install -e .
```

### Connect Hardware
1. Plug XIAO into Mac via USB
2. Power on Tobii Recording Unit
3. Connect Mac to Tobii WiFi network

### Run
```bash
# Breathing only
python examples/print_data.py
python examples/live_plot.py
python examples/save_to_csv.py

# Gaze + breathing synchronized
python examples/gaze_breath.py
```

## Project Structure
nasal_monitor/
├── nasal_monitor/
│   ├── reader.py          # XIAO serial reader
│   ├── detector.py        # breath detection
│   ├── models.py          # data classes
│   ├── tobii_reader.py    # Tobii gaze reader
│   └── synchronizer.py   # timestamp sync
└── examples/

## Configuration
```python
# Adjust breath detection sensitivity
monitor = NasalMonitor(threshold=80)

# Set which nostril each mic is on
monitor = NasalMonitor(mic1_side="left", mic2_side="right")
```