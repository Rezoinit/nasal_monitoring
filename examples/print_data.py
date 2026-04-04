# Simplest possible usage — print everything
from nasal_monitor import NasalMonitor

monitor = NasalMonitor()   # auto-detects port

@monitor.on_reading
def on_reading(r):
    print(f"t={r.timestamp_ms}ms  "
          f"mic1={r.mic1:4d}  "
          f"mic2={r.mic2:4d}  "
          f"side={r.side}")

@monitor.on_breath
def on_breath(event):
    print(f"\n🌬️  BREATH EVENT")
    print(f"   side      : {event.side}")
    print(f"   intensity : {event.intensity:.2f}")
    if event.duration_ms:
        print(f"   duration  : {event.duration_ms:.0f}ms\n")

monitor.start_blocking()