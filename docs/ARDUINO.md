# Arduino Sketch

Located in `arduino/XIAO_SensorReader/XIAO_SensorReader.ino`.

---

## Output Format

One JSON line per reading at approximately **100–200 Hz** over USB Serial at 115200 baud.
Rate is limited by Serial bandwidth — downsampling to a target Hz is handled in the Python pipeline.

    {"t":37473,"seq":285,"m1":2051,"m2":2038,"temp":124}

| Field | Type | Description |
|---|---|---|
| t | uint32 | millis() — milliseconds since board boot |
| seq | uint32 | Packet sequence number — detects dropped packets |
| m1 | int | MIC1 raw ADC, yellow wire (0–4095, ~2048 at rest) |
| m2 | int | MIC2 raw ADC, blue wire (0–4095, ~2048 at rest) |
| temp | int32 | Chip die temperature raw — divide by 4.0 for °C |

On startup the board also emits one status line:

    {"status":"ready","board":"xiao_nrf52840","boot_ms":2}

---

## Design Notes

- **Raw ADC, no processing on board** — values are instantaneous ADC readings, not peak-to-peak
- To recover peak-to-peak amplitude (the breathing signal envelope), use `NasalMonitor(target_hz=8)` in Python, or the JavaScript accumulator in the web app
- Chip temperature read via direct nRF52840 TEMP register access
- Sequence counter detects dropped packets during post-hoc analysis
- `millis()` timestamp enables a time anchor in the Python library to convert board time to real-world Unix time

---

## Key Constants

| Constant | Default | Description |
|---|---|---|
| BAUD_RATE | 115200 | Serial baud rate — must match Python library |
