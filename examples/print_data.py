# examples/print_data.py
# ─────────────────────────────────────────────────
# Simplest usage — print raw readings.
# Raw mode: no threshold, no classification.
# ─────────────────────────────────────────────────
from nasal_monitor import NasalMonitor

# Raw mode — no live detection
monitor = NasalMonitor()

@monitor.on_reading
def on_reading(r):
    print(
        f"seq={r.seq:5d}  "
        f"t={r.timestamp_ms:8d}ms  "
        f"mic1={r.mic1:4d}  "
        f"mic2={r.mic2:4d}  "
        f"temp={r.chip_temp_c:.1f}°C"
    )

monitor.start_blocking()