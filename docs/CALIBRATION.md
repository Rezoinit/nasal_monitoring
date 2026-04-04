# Calibration Tool

The threshold calibration tool finds per-participant signal thresholds before a study session. Thresholds are saved to a JSON file and applied during post-hoc analysis only — raw data recording is never affected.

---

## Running the Tool

    python analysis/threshold_server.py

Chrome opens automatically at `http://localhost:5500`.

---

## Workflow

1. Enter participant ID and optional session notes
2. Overview screen shows all 8 scenarios
3. For each scenario:
   - Get Ready screen shows the instruction
   - Press **Space** or click **I'm Ready** to begin
   - Circular countdown runs for the scenario duration
   - 5-second rest between scenarios
4. Results screen shows threshold recommendations
5. Two files are saved automatically to `calibration/`

---

## Scenarios

| Scenario | Duration | Purpose |
|---|---|---|
| Baseline | 30s | Normal resting breathing — establishes noise floor |
| Mouth only | 20s | True noise floor with no nasal signal |
| Left nostril | 20s | Left mic reference signal level |
| Right nostril | 20s | Right mic reference signal level |
| Deep breathing | 20s | Upper signal range |
| Shallow breathing | 20s | Lower breath signal threshold |
| Talking | 20s | Speech and vibration artefact characterisation |
| Head movement | 20s | Motion artefact characterisation |

---

## Output Files

    calibration/
    ├── raw_P01_1718123456.csv          ← full raw data, all scenarios
    └── thresholds_P01_1718123456.json  ← threshold recommendations

### Threshold JSON structure

    {
      "metadata": { "participant_id": "P01", ... },
      "recommendations": {
        "mic1": {
          "aggressive":   70.2,   ← catches subtle breaths, more false positives
          "recommended":  78.5,   ← good balance for most participants
          "conservative": 89.0    ← only clear breaths, fewest false positives
        },
        "mic2": { ... }
      },
      "scenario_stats": { ... }   ← full statistics per scenario
    }

### Calibration CSV columns

| Column | Description |
|---|---|
| host_time | Mac Unix timestamp |
| board_ms | nRF millis() since boot |
| seq | Packet sequence number |
| mic1 | Yellow mic raw |
| mic2 | Blue mic raw |
| chip_temp_c | Chip temperature °C |
| scenario | Which scenario was active |

---

## Threshold Recommendations

Three threshold levels are provided per microphone:

- **Aggressive** — mean + 1 std above baseline. Catches even subtle nasal airflow. Suitable when sensitivity is more important than specificity.
- **Recommended** — mean + 2 std above baseline. Good balance for most participants and scenarios.
- **Conservative** — 99th percentile of baseline signal. Only fires on clearly detectable breath events. Minimises false positives.

The right choice depends on your research question and the participant's breathing pattern. If in doubt, record with no threshold and compare all three during analysis.

---

## Dependencies

    pip install flask flask-socketio pyserial