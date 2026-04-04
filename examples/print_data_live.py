# examples/print_data_live.py
# ─────────────────────────────────────────────────
# Print raw readings WITH live breath detection.
# Useful for verifying detector behaviour.
# Detection does NOT affect saved data.
# ─────────────────────────────────────────────────
from nasal_monitor import NasalMonitor

# Enable live detection for real-time feedback
monitor = NasalMonitor(
    live_detection = True,
    sensitivity    = 2.0,    # adjust if needed
    min_breath_ms  = 300,
)

@monitor.on_reading
def on_reading(r):
    # Show current adaptive thresholds alongside data
    thresh = monitor.current_thresholds
    t1 = thresh["mic1_threshold"] if thresh else "?"
    t2 = thresh["mic2_threshold"] if thresh else "?"
    print(
        f"seq={r.seq:5d}  "
        f"mic1={r.mic1:4d}(thr:{t1:.0f})  "
        f"mic2={r.mic2:4d}(thr:{t2:.0f})  "
        f"temp={r.chip_temp_c:.1f}°C"
    )

@monitor.on_breath
def on_breath(event):
    print(f"\n🌬️  BREATH EVENT")
    print(f"   side      : {event.side}")
    print(f"   intensity : {event.intensity:.3f}")
    print(f"   board_ms  : {event.board_ms}")
    print(f"   seq       : {event.seq}")
    if event.duration_ms:
        print(f"   duration  : {event.duration_ms:.0f}ms\n")

monitor.start_blocking()