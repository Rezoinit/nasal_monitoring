import collections
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from nasal_monitor import TobiiReader

TRAIL = 50      # gaze trail length
HISTORY = 100   # pupil plot history

# Rolling buffers
gaze_x  = collections.deque([0.5] * TRAIL,    maxlen=TRAIL)
gaze_y  = collections.deque([0.5] * TRAIL,    maxlen=TRAIL)
pd_left  = collections.deque([0.0] * HISTORY, maxlen=HISTORY)
pd_right = collections.deque([0.0] * HISTORY, maxlen=HISTORY)
is_valid = collections.deque([False] * TRAIL,  maxlen=TRAIL)

tobii = TobiiReader("192.168.71.50")

@tobii.on_gaze
def on_gaze(g):
    gaze_x.append(g.gaze_x)
    gaze_y.append(g.gaze_y)
    is_valid.append(g.valid)
    pd_left.append(g.pupil_left   if g.pupil_left  > 0 else None)
    pd_right.append(g.pupil_right if g.pupil_right > 0 else None)

# ── Layout ────────────────────────────────────────
fig, (ax_gaze, ax_pupil) = plt.subplots(
    1, 2, figsize=(13, 6),
    gridspec_kw={"width_ratios": [1, 1.4]}
)
fig.suptitle("Tobii Pro Glasses 2 — Live Gaze", fontsize=13)

# ── Gaze panel ────────────────────────────────────
ax_gaze.set_xlim(0, 1)
ax_gaze.set_ylim(1, 0)   # y-axis flipped: 0=top, 1=bottom
ax_gaze.set_aspect("equal")
ax_gaze.set_facecolor("#1a1a2e")
ax_gaze.set_title("Gaze Position", fontsize=10)
ax_gaze.set_xlabel("X (left → right)")
ax_gaze.set_ylabel("Y (top → bottom)")
ax_gaze.grid(True, alpha=0.15, color="white")

trail_line, = ax_gaze.plot([], [], color="#4a90e2", alpha=0.4, linewidth=1)
gaze_dot,   = ax_gaze.plot([], [], "o", color="white", markersize=10, zorder=5)
status_text  = ax_gaze.text(
    0.02, 0.97, "", transform=ax_gaze.transAxes,
    color="white", fontsize=8, va="top"
)

# ── Pupil panel ───────────────────────────────────
ax_pupil.set_xlim(0, HISTORY)
ax_pupil.set_ylim(1.5, 9.0)
ax_pupil.set_title("Pupil Diameter", fontsize=10)
ax_pupil.set_xlabel("Samples (newest right)")
ax_pupil.set_ylabel("Diameter (mm)")
ax_pupil.grid(True, alpha=0.3)

line_left,  = ax_pupil.plot([], [], color="#f5a623", label="Left",  linewidth=1.5)
line_right, = ax_pupil.plot([], [], color="#4a90e2", label="Right", linewidth=1.5)
ax_pupil.legend(loc="upper right", fontsize=8)

x_hist = list(range(HISTORY))

# ── Animation ─────────────────────────────────────
def update(_):
    xs = list(gaze_x)
    ys = list(gaze_y)
    valid = list(is_valid)

    # Trail
    trail_line.set_data(xs, ys)

    # Current dot — colour by validity
    dot_color = "white" if valid[-1] else "red"
    gaze_dot.set_data([xs[-1]], [ys[-1]])
    gaze_dot.set_color(dot_color)

    status_text.set_text(
        f"x={xs[-1]:.3f}  y={ys[-1]:.3f}\n"
        f"{'VALID' if valid[-1] else 'LOST'}"
    )
    status_text.set_color("white" if valid[-1] else "red")

    # Pupils — skip None
    left_vals  = [v if v is not None else float("nan") for v in pd_left]
    right_vals = [v if v is not None else float("nan") for v in pd_right]
    line_left.set_data(x_hist,  left_vals)
    line_right.set_data(x_hist, right_vals)

    return trail_line, gaze_dot, status_text, line_left, line_right

ani = animation.FuncAnimation(fig, update, interval=50, blit=False)

tobii.start()
plt.tight_layout()
plt.show()
tobii.stop()
