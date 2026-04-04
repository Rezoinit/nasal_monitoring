# Real-time scrolling graph of both mic channels
import collections
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from nasal_monitor import NasalMonitor

HISTORY = 100   # number of readings to show on screen

# Rolling buffers — oldest data falls off the left
mic1_data = collections.deque([0] * HISTORY, maxlen=HISTORY)
mic2_data = collections.deque([0] * HISTORY, maxlen=HISTORY)
side_data = collections.deque(["none"] * HISTORY, maxlen=HISTORY)

monitor = NasalMonitor()

@monitor.on_reading
def on_reading(r):
    mic1_data.append(r.mic1)
    mic2_data.append(r.mic2)
    side_data.append(r.side)

# ── Matplotlib setup ──────────────────────────────
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 5))
fig.suptitle("Nasal Breathing Monitor", fontsize=14)

line1, = ax1.plot(list(mic1_data), color="#f5a623", label="MIC1 Yellow")
line2, = ax2.plot(list(mic2_data), color="#4a90e2", label="MIC2 Blue")

for ax in (ax1, ax2):
    ax.set_ylim(0, 500)
    ax.set_xlim(0, HISTORY)
    ax.legend(loc="upper right")
    ax.set_ylabel("Volume")
    ax.axhline(y=80, color="red",
               linestyle="--", linewidth=0.8,
               label="threshold")

ax2.set_xlabel("Readings")

def update(_frame):
    line1.set_ydata(list(mic1_data))
    line2.set_ydata(list(mic2_data))

    # Colour background based on breath side
    side = side_data[-1]
    colour = {
        "left"  : "#fff3cd",
        "right" : "#d1ecf1",
        "both"  : "#f8d7da",
        "none"  : "#ffffff"
    }.get(side, "#ffffff")

    fig.patch.set_facecolor(colour)
    return line1, line2

ani = animation.FuncAnimation(
    fig, update,
    interval=100,    # refresh every 100ms
    blit=False
)

monitor.start()   # non-blocking — matplotlib takes over main thread
plt.tight_layout()
plt.show()