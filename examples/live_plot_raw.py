# examples/live_plot_raw.py
# ─────────────────────────────────────────────────
# Real-time scrolling plot of raw ADC signal.
# Full rate (~100–200 Hz) — instantaneous ADC values.
# No downsampling. No data is saved — purely visual.
# ─────────────────────────────────────────────────
import collections
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from nasal_monitor import NasalMonitor

HISTORY = 300   # ~2 seconds at ~150 Hz

# Rolling data buffers — raw ADC values (0–4095)
mic1_data = collections.deque([0] * HISTORY, maxlen=HISTORY)
mic2_data = collections.deque([0] * HISTORY, maxlen=HISTORY)

# Full rate — no downsampling
monitor = NasalMonitor()

@monitor.on_reading
def on_reading(r):
    mic1_data.append(r.mic1)
    mic2_data.append(r.mic2)

# ── Matplotlib ────────────────────────────────────
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 6))
fig.suptitle("Nasal Breathing Monitor — Raw ADC (~150 Hz)", fontsize=14)

line1, = ax1.plot([], [], color="#f5a623",
                  label="MIC1 Yellow (raw ADC)", linewidth=1.0)
line2, = ax2.plot([], [], color="#4a90e2",
                  label="MIC2 Blue (raw ADC)", linewidth=1.0)

for ax in (ax1, ax2):
    ax.set_ylim(0, 4095)
    ax.set_xlim(0, HISTORY)
    ax.legend(loc="upper right", fontsize=8)
    ax.set_ylabel("Raw ADC value (0–4095)")
    ax.grid(True, alpha=0.3)

ax1.set_title("MIC1 — Yellow wire — left nostril")
ax2.set_title("MIC2 — Blue wire — right nostril")
ax2.set_xlabel("Readings, newest on right (~2 s window)")

x = list(range(HISTORY))

def update(_frame):
    line1.set_data(x, list(mic1_data))
    line2.set_data(x, list(mic2_data))
    return line1, line2

ani = animation.FuncAnimation(
    fig, update,
    interval=50,   # refresh every 50 ms — faster to keep up with high rate
    blit=False
)

monitor.start()
plt.tight_layout()
plt.show()
