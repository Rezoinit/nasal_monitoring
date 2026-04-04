# Arduino Sketch

Located in the Arduino IDE project `XIAO_SensorReader`.

---

## Output Format

One JSON line per reading at approximately 8 Hz over USB Serial at 115200 baud.

    {"t":37473,"seq":285,"m1":78,"m2":42,"temp":124}

| Field | Type | Description |
|---|---|---|
| t | uint32 | millis() — milliseconds since board boot |
| seq | uint32 | Packet sequence number — detects dropped packets |
| m1 | int | MIC1 peak-to-peak amplitude, yellow wire (0–4095) |
| m2 | int | MIC2 peak-to-peak amplitude, blue wire (0–4095) |
| temp | int32 | Chip die temperature raw — divide by 4.0 for °C |

On startup the board also emits one status line:

    {"status":"ready","board":"xiao_nrf52840","boot_ms":2}

---

## Key Constants

| Constant | Default | Description |
|---|---|---|
| SAMPLE_WINDOW_MS | 60 | Sampling window per reading in milliseconds |
| BAUD_RATE | 115200 | Serial baud rate — must match Python library |

---

## Design Notes

- No threshold logic on the board — all values are raw
- Peak-to-peak amplitude used instead of mean to capture transient breath events
- Chip temperature read via direct nRF52840 TEMP register access
- Sequence counter detects dropped packets during post-hoc analysis
- `millis()` timestamp enables a time anchor in the Python library to convert board time to real-world Unix time