# examples/live_plot.py
# ─────────────────────────────────────────────────
# Real-time scrolling plot of breathing signal.
# Downsampled to 8 Hz — shows peak-to-peak amplitude
# per 125 ms window, same as old firmware behaviour.
# No data is saved here — purely visual.
# ─────────────────────────────────────────────────
import collections
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from nasal_monitor import NasalMonitor

TARGET_HZ = 8
HISTORY   = TARGET_HZ * 15   # 15 seconds of history

# Rolling data buffers — peak-to-peak per window
mic1_data = collections.deque([0] * HISTORY, maxlen=HISTORY)
mic2_data = collections.deque([0] * HISTORY, maxlen=HISTORY)

# Downsample to 8 Hz so mic values are peak-to-peak amplitude
monitor = NasalMonitor(target_hz=TARGET_HZ)

@monitor.on_reading
def on_reading(r):
    mic1_data.append(r.mic1)
    mic2_data.append(r.mic2)

# ── Matplotlib ────────────────────────────────────
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 6))
fig.suptitle("Nasal Breathing Monitor — Peak-to-peak signal (8 Hz)", fontsize=14)

line1, = ax1.plot([], [], color="#f5a623",
                  label="MIC1 Yellow (p2p)", linewidth=1.5)
line2, = ax2.plot([], [], color="#4a90e2",
                  label="MIC2 Blue (p2p)", linewidth=1.5)

for ax in (ax1, ax2):
    ax.set_ylim(0, 500)
    ax.set_xlim(0, HISTORY)
    ax.legend(loc="upper right", fontsize=8)
    ax.set_ylabel("Peak-to-peak amplitude")
    ax.grid(True, alpha=0.3)

ax1.set_title("MIC1 — Yellow wire — left nostril")
ax2.set_title("MIC2 — Blue wire — right nostril")
ax2.set_xlabel(f"Readings at {TARGET_HZ} Hz (newest on right)")

x = list(range(HISTORY))

def update(_frame):
    line1.set_data(x, list(mic1_data))
    line2.set_data(x, list(mic2_data))
    return line1, line2

ani = animation.FuncAnimation(
    fig, update,
    interval=100,
    blit=False
)

monitor.start()
plt.tight_layout()
plt.show()