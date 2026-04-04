# examples/gaze_breath.py
# ─────────────────────────────────────────────────
# Full synchronized session:
# Tobii gaze + XIAO nasal breathing → CSV file
#
# BEFORE RUNNING:
#   1. Power on Tobii Recording Unit
#   2. Connect Mac to Tobii WiFi network
#   3. Find Tobii IP (see below)
#   4. Plug XIAO into Mac via USB
# ─────────────────────────────────────────────────

import csv
import time
from nasal_monitor import NasalMonitor, TobiiReader, Synchronizer

# ── CONFIGURATION ─────────────────────────────────
# Option A: Auto-discover Tobii IP
TOBII_IP = TobiiReader.discover()

# Option B: Set IP manually if you know it
# TOBII_IP = "192.168.71.50"

OUTPUT_FILE = f"session_{int(time.time())}.csv"
# ─────────────────────────────────────────────────

xiao  = NasalMonitor()         # auto-detects USB port
tobii = TobiiReader(TOBII_IP)
sync  = Synchronizer(xiao, tobii)

with open(OUTPUT_FILE, "w", newline="") as f:
    writer = csv.writer(f)

    # Header row
    writer.writerow([
        "host_time",
        "gaze_x", "gaze_y",
        "pupil_left", "pupil_right", "gaze_valid",
        "breath_side", "breath_intensity",
        "mic1_raw", "mic2_raw",
    ])

    @sync.on_event
    def handle(event):
        # Save to CSV
        writer.writerow([
            f"{event.host_time:.4f}",
            f"{event.gaze_x:.4f}",
            f"{event.gaze_y:.4f}",
            f"{event.pupil_left:.2f}",
            f"{event.pupil_right:.2f}",
            event.gaze_valid,
            event.breath_side,
            f"{event.breath_intensity:.2f}",
            event.mic1_raw,
            event.mic2_raw,
        ])
        f.flush()

        # Print live summary
        gaze_str = (
            f"gaze=({event.gaze_x:.2f},{event.gaze_y:.2f})"
            if event.gaze_valid
            else "gaze=INVALID"
        )
        print(
            f"{gaze_str}  "
            f"pupil=({event.pupil_left:.1f},{event.pupil_right:.1f})  "
            f"breath={event.breath_side:6s}  "
            f"intensity={event.breath_intensity:.2f}"
        )

    print(f"Recording to {OUTPUT_FILE}")
    print("Press Ctrl+C to stop.")
    sync.start_blocking()

print(f"\nSession saved to {OUTPUT_FILE}")