# Quick connection test — prints raw readings for 10 seconds.
from nasal_monitor import NasalMonitor
import time

monitor = NasalMonitor()

@monitor.on_reading
def on_reading(r):
    print(
        f"seq={r.seq:5d}  "
        f"mic1={r.mic1:4d}  "
        f"mic2={r.mic2:4d}  "
        f"temp={r.chip_temp_c:.1f}°C"
    )

monitor.start()
time.sleep(10)
monitor.stop()
