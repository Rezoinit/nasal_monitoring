# examples/save_to_csv.py
# ─────────────────────────────────────────────────
# Record a full session to CSV.
# Saves ALL raw data — nothing filtered or removed.
# ─────────────────────────────────────────────────
import csv
import time
from nasal_monitor import NasalMonitor

OUTPUT_FILE = f"session_{int(time.time())}.csv"
monitor     = NasalMonitor()   # raw mode — no detection

with open(OUTPUT_FILE, "w", newline="") as f:
    writer = csv.writer(f)

    # Full header — every field saved
    writer.writerow([
        "host_time",      # Mac Unix timestamp (float)
        "board_ms",       # nRF millis() since boot
        "seq",            # packet sequence number
        "mic1",           # yellow mic raw (0–4095)
        "mic2",           # blue mic raw   (0–4095)
        "chip_temp_c",    # chip temperature °C
    ])

    @monitor.on_reading
    def on_reading(r):
        writer.writerow([
            f"{r.host_time:.4f}",
            r.timestamp_ms,
            r.seq,
            r.mic1,
            r.mic2,
            f"{r.chip_temp_c:.2f}",
        ])
        f.flush()   # write immediately — no buffering
        print(
            f"seq={r.seq:5d}  "
            f"mic1={r.mic1:4d}  "
            f"mic2={r.mic2:4d}  "
            f"temp={r.chip_temp_c:.1f}°C"
        )

    print(f"[Recording] Saving to: {OUTPUT_FILE}")
    print("[Recording] Press Ctrl+C to stop.")
    monitor.start_blocking()

print(f"\n[Recording] Complete. Saved to {OUTPUT_FILE}")