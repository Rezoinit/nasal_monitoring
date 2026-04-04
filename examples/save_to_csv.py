# Record a session to CSV file
import csv
import time
from nasal_monitor import NasalMonitor

OUTPUT_FILE = "breathing_session.csv"

monitor = NasalMonitor()

with open(OUTPUT_FILE, "w", newline="") as f:
    writer = csv.writer(f)

    # Write header row
    writer.writerow([
        "host_time", "board_ms",
        "mic1", "mic2", "side"
    ])

    @monitor.on_reading
    def on_reading(r):
        writer.writerow([
            f"{r.host_time:.4f}",
            r.timestamp_ms,
            r.mic1,
            r.mic2,
            r.side
        ])
        f.flush()   # write to disk immediately, don't buffer
        print(f"  {r.side:6s}  mic1={r.mic1:4d}  mic2={r.mic2:4d}")

    print(f"Recording to {OUTPUT_FILE} — press Ctrl+C to stop")
    monitor.start_blocking()

print(f"\nSaved to {OUTPUT_FILE}")