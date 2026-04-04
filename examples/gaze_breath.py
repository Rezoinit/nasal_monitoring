# examples/gaze_breath.py
# ─────────────────────────────────────────────────
# Full synchronized session recording.
# Tobii gaze + XIAO breathing → CSV file.
# All raw values saved — no filtering.
#
# BEFORE RUNNING:
#   1. Power on Tobii Recording Unit
#   2. Connect Mac to Tobii WiFi
#   3. Plug XIAO into Mac via USB
# ─────────────────────────────────────────────────
import csv
import time
from nasal_monitor import NasalMonitor, TobiiReader, Synchronizer

# ── CONFIGURATION ─────────────────────────────────
TOBII_IP    = TobiiReader.discover()   # auto-find Tobii
# TOBII_IP  = "192.168.71.50"          # or set manually
OUTPUT_FILE = f"gaze_breath_{int(time.time())}.csv"
# ─────────────────────────────────────────────────

xiao  = NasalMonitor()
tobii = TobiiReader(TOBII_IP)
sync  = Synchronizer(xiao, tobii)

with open(OUTPUT_FILE, "w", newline="") as f:
    writer = csv.writer(f)

    # Full header — every raw field
    writer.writerow([
        "host_time",      # Mac Unix timestamp
        "board_ms",       # nRF board millis()
        "seq",            # packet sequence number
        "mic1",           # yellow mic raw
        "mic2",           # blue mic raw
        "chip_temp_c",    # chip temperature °C
        "gaze_x",         # 0.0–1.0 or -1 if invalid
        "gaze_y",         # 0.0–1.0 or -1 if invalid
        "pupil_left",     # mm or -1 if invalid
        "pupil_right",    # mm or -1 if invalid
        "gaze_valid",     # True/False
    ])

    @sync.on_event
    def handle(event):
        writer.writerow([
            f"{event.host_time:.4f}",
            event.board_ms,
            event.seq,
            event.mic1_raw,
            event.mic2_raw,
            f"{event.chip_temp_c:.2f}",
            f"{event.gaze_x:.4f}",
            f"{event.gaze_y:.4f}",
            f"{event.pupil_left:.2f}",
            f"{event.pupil_right:.2f}",
            event.gaze_valid,
        ])
        f.flush()

        # Live terminal summary
        gaze_str = (
            f"gaze=({event.gaze_x:.2f},{event.gaze_y:.2f})"
            if event.gaze_valid else "gaze=INVALID    "
        )
        print(
            f"seq={event.seq:5d}  "
            f"{gaze_str}  "
            f"mic1={event.mic1_raw:4d}  "
            f"mic2={event.mic2_raw:4d}  "
            f"temp={event.chip_temp_c:.1f}°C"
        )

    print(f"[Session] Recording to: {OUTPUT_FILE}")
    print("[Session] Press Ctrl+C to stop.")
    sync.start_blocking()

print(f"\n[Session] Complete. Saved to {OUTPUT_FILE}")