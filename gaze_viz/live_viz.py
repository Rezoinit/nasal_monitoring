"""
gaze_viz/live_viz.py
─────────────────────────────────────────────────────────────────
Tobii Pro Glasses 2 — comprehensive live visualization.

All available data streams in one display:

  ┌──────────────────┬──────────┬──────────┬──────────────┐
  │   Gaze Map       │ Left Eye │ Right Eye│  Data Panel  │
  │   (2D screen)    │ animated │ animated │  (all values)│
  ├──────────────────┴──────────┴──────────┤              │
  │   Pupil Diameter  (L + R scrolling)    │              │
  ├────────────────────────────────────────┤              │
  │   Accelerometer  (x / y / z)          │              │
  ├────────────────────────────────────────┤              │
  │   Gyroscope      (x / y / z)          │              │
  └────────────────────────────────────────┴──────────────┘

Run:
    python gaze_viz/live_viz.py
"""

import collections
import time
import threading
import math
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
from tobiiglassesctrl import TobiiGlassesController

# ── Config ────────────────────────────────────────────────────
TOBII_IP   = "192.168.71.50"
HISTORY    = 200   # samples in scrolling plots
TRAIL      = 80    # gaze trail length
REFRESH_MS = 50    # animation refresh

# ── Colour palette ────────────────────────────────────────────
BG     = "#0d1117"
PANEL  = "#111827"
BORDER = "#1f2937"
TEXT   = "#e5e7eb"
DIM    = "#4b5563"
ORA    = "#f59e0b"   # left eye
BLU    = "#3b82f6"   # right eye
GRN    = "#34d399"   # valid
RED_C  = "#ef4444"   # invalid / lost
CYN    = "#22d3ee"   # 3D gaze
ACC_CL = ["#ef4444", "#10b981", "#3b82f6"]   # accel x/y/z
GYR_CL = ["#f97316", "#a78bfa", "#22d3ee"]   # gyro  x/y/z

# ── Rolling buffers ───────────────────────────────────────────
gaze_xs = collections.deque([0.5] * TRAIL,    maxlen=TRAIL)
gaze_ys = collections.deque([0.5] * TRAIL,    maxlen=TRAIL)
pd_L    = collections.deque([3.0] * HISTORY,  maxlen=HISTORY)
pd_R    = collections.deque([3.0] * HISTORY,  maxlen=HISTORY)
acc_buf = [collections.deque([0.0] * HISTORY, maxlen=HISTORY) for _ in range(3)]
gyr_buf = [collections.deque([0.0] * HISTORY, maxlen=HISTORY) for _ in range(3)]
acc_buf[1] = collections.deque([-9.8] * HISTORY, maxlen=HISTORY)   # gravity on y

# ── Shared state ──────────────────────────────────────────────
latest = {
    "gaze_x": 0.5,  "gaze_y": 0.5,
    "gp3":  [0.0, 0.0, 0.0],
    "pd_l": 3.0,    "pd_r": 3.0,
    "gd_l": [0.0, 0.0, 1.0],
    "gd_r": [0.0, 0.0, 1.0],
    "pc_l": [0.0, 0.0, 0.0],
    "pc_r": [0.0, 0.0, 0.0],
    "acc":  [0.0, -9.8, 0.0],
    "gyr":  [0.0,  0.0, 0.0],
    "valid": False,
    "vergence": 0.0,
    "sample_rate": 0.0,
    "quality": 0.0,
}

_counters    = [0, 0]          # [valid_frames, total_frames]
_frame_times = collections.deque(maxlen=50)


# ── Helpers ───────────────────────────────────────────────────
def _vergence(gd_l, gd_r) -> float:
    dot = max(-1.0, min(1.0, sum(a * b for a, b in zip(gd_l, gd_r))))
    return math.degrees(math.acos(dot))

def pd_to_r(pd_mm: float) -> float:
    return max(0.07, min(0.37, 0.07 + (pd_mm - 2.0) * 0.05))

def gd_to_xy(gd: list, scale: float = 0.48):
    return (max(-0.28, min(0.28,  gd[0] * scale)),
            max(-0.22, min(0.22, -gd[1] * scale)))


# ── Tobii background thread ───────────────────────────────────
tobii = TobiiGlassesController(TOBII_IP, video_scene=False)
tobii.start_streaming()

def _read_loop():
    while True:
        try:
            d = tobii.get_data()
            _frame_times.append(time.time())
            _counters[1] += 1

            gp = d.get("gp", {}).get("gp")
            if gp and len(gp) == 2:
                latest["gaze_x"] = gp[0]
                latest["gaze_y"] = gp[1]
                gaze_xs.append(gp[0])
                gaze_ys.append(gp[1])

            gp3 = d.get("gp3", {}).get("gp3")
            if gp3 and len(gp3) == 3:
                latest["gp3"] = gp3

            v = d.get("gp", {}).get("s", 1) == 0
            latest["valid"] = v
            if v:
                _counters[0] += 1

            for side, k in (("left_eye", "l"), ("right_eye", "r")):
                eye = d.get(side, {})
                pd  = eye.get("pd", {}).get("pd", -1)
                gd  = eye.get("gd", {}).get("gd")
                pc  = eye.get("pc", {}).get("pc")
                buf = pd_L if k == "l" else pd_R
                if pd > 0:
                    latest[f"pd_{k}"] = pd
                    buf.append(pd)
                if gd and len(gd) == 3:
                    latest[f"gd_{k}"] = gd
                if pc and len(pc) == 3:
                    latest[f"pc_{k}"] = pc

            acc = d.get("mems", {}).get("ac", {}).get("ac")
            gyr = d.get("mems", {}).get("gy", {}).get("gy")
            if acc and len(acc) == 3:
                latest["acc"] = acc
                for i in range(3):
                    acc_buf[i].append(acc[i])
            if gyr and len(gyr) == 3:
                latest["gyr"] = gyr
                for i in range(3):
                    gyr_buf[i].append(gyr[i])

            latest["vergence"] = _vergence(latest["gd_l"], latest["gd_r"])

            if len(_frame_times) >= 2:
                dt = _frame_times[-1] - _frame_times[0]
                if dt > 0:
                    latest["sample_rate"] = (len(_frame_times) - 1) / dt
            if _counters[1] > 0:
                latest["quality"] = 100.0 * _counters[0] / _counters[1]

            time.sleep(0.005)
        except Exception:
            time.sleep(0.05)

threading.Thread(target=_read_loop, daemon=True).start()


# ── Figure ────────────────────────────────────────────────────
fig = plt.figure(figsize=(20, 11), facecolor=BG)
fig.suptitle("Tobii Pro Glasses 2 — Live Data",
             color=TEXT, fontsize=12, x=0.41, y=0.985)

gs = gridspec.GridSpec(
    4, 5, figure=fig,
    height_ratios=[2.4, 1.0, 0.88, 0.88],
    width_ratios=[1.25, 1.25, 1.0, 1.0, 1.05],
    hspace=0.44, wspace=0.28,
    left=0.04, right=0.98, top=0.95, bottom=0.05,
)

ax_gaze  = fig.add_subplot(gs[0, 0:2])
ax_left  = fig.add_subplot(gs[0, 2])
ax_right = fig.add_subplot(gs[0, 3])
ax_data  = fig.add_subplot(gs[0:4, 4])
ax_pd    = fig.add_subplot(gs[1, 0:4])
ax_acc   = fig.add_subplot(gs[2, 0:4])
ax_gyr   = fig.add_subplot(gs[3, 0:4])

for ax in (ax_gaze, ax_left, ax_right, ax_pd, ax_acc, ax_gyr):
    ax.set_facecolor(PANEL)
    for sp in ax.spines.values():
        sp.set_edgecolor(BORDER)

ax_data.set_facecolor(BG)
ax_data.axis("off")


# ── Gaze map ──────────────────────────────────────────────────
ax_gaze.set_xlim(0, 1)
ax_gaze.set_ylim(1, 0)
ax_gaze.set_title("Gaze Position", color=TEXT, fontsize=9, pad=5)
ax_gaze.set_xlabel("X  (left → right)", color=DIM, fontsize=7.5)
ax_gaze.set_ylabel("Y  (top → bottom)", color=DIM, fontsize=7.5)
ax_gaze.tick_params(colors=DIM, labelsize=6.5)
ax_gaze.grid(True, alpha=0.08, color="white")
for sp in ax_gaze.spines.values():
    sp.set_linewidth(1.2)
    sp.set_edgecolor("#374151")

gaze_trail, = ax_gaze.plot([], [], color=BLU, alpha=0.3, linewidth=1.2)
gaze_dot,   = ax_gaze.plot([], [], "o", color=TEXT, markersize=10, zorder=5,
                            markeredgecolor=BLU, markeredgewidth=1.8)
gaze_status  = ax_gaze.text(0.02, 0.05, "", transform=ax_gaze.transAxes,
                             color=GRN, fontsize=7.5, va="bottom", family="monospace")


# ── Eye panels ────────────────────────────────────────────────
def _build_eye(ax, title, iris_col):
    ax.set_xlim(-1, 1)
    ax.set_ylim(-0.7, 0.7)
    ax.set_aspect("equal")
    ax.set_title(title, color=TEXT, fontsize=9, pad=5)
    ax.set_xticks([])
    ax.set_yticks([])
    for p in (mpatches.Ellipse((0, 0), 2.1,  1.5,  color=PANEL,     zorder=0),
              mpatches.Ellipse((0, 0), 1.85, 1.15, color="#f0ede4", zorder=1),
              mpatches.Circle( (0, 0), 0.45,        color="#14202e", zorder=2)):
        ax.add_patch(p)
    iris   = mpatches.Circle((0, 0), 0.42, color=iris_col,  zorder=3)
    pupil  = mpatches.Circle((0, 0), 0.18, color="#080808", zorder=4)
    hilite = mpatches.Ellipse((0.10, 0.15), 0.13, 0.09,
                               color="white", alpha=0.50, zorder=5)
    for p in (iris, pupil, hilite):
        ax.add_patch(p)
    pdtxt = ax.text(0, -0.62, "pd  --", ha="center",
                    color=DIM, fontsize=7.5, zorder=6)
    return iris, pupil, hilite, pdtxt

iris_L, pupil_L, hl_L, pdtxt_L = _build_eye(ax_left,  "Left Eye",  "#2d5fa0")
iris_R, pupil_R, hl_R, pdtxt_R = _build_eye(ax_right, "Right Eye", "#1a6640")


# ── Pupil trace ───────────────────────────────────────────────
ax_pd.set_xlim(0, HISTORY)
ax_pd.set_ylim(1.5, 9.0)
ax_pd.set_title("Pupil Diameter", color=TEXT, fontsize=9, pad=5)
ax_pd.set_ylabel("mm", color=DIM, fontsize=7.5)
ax_pd.tick_params(colors=DIM, labelsize=6.5)
ax_pd.set_xticks([])
ax_pd.grid(True, alpha=0.08, color="white")
line_pdL, = ax_pd.plot([], [], color=ORA, linewidth=1.5, label="Left")
line_pdR, = ax_pd.plot([], [], color=BLU, linewidth=1.5, label="Right")
ax_pd.legend(loc="upper right", fontsize=7, labelcolor=TEXT,
             facecolor=PANEL, edgecolor=BORDER)


# ── Accelerometer ─────────────────────────────────────────────
ax_acc.set_xlim(0, HISTORY)
ax_acc.set_ylim(-15, 15)
ax_acc.set_title("Accelerometer", color=TEXT, fontsize=9, pad=5)
ax_acc.set_ylabel("m/s²", color=DIM, fontsize=7.5)
ax_acc.tick_params(colors=DIM, labelsize=6.5)
ax_acc.set_xticks([])
ax_acc.grid(True, alpha=0.08, color="white")
ax_acc.axhline(0, color=BORDER, linewidth=0.7)
acc_lines = [ax_acc.plot([], [], color=c, linewidth=1.2, label=l)[0]
             for c, l in zip(ACC_CL, ["x", "y", "z"])]
ax_acc.legend(loc="upper right", fontsize=7, labelcolor=TEXT,
              facecolor=PANEL, edgecolor=BORDER, ncol=3)


# ── Gyroscope ─────────────────────────────────────────────────
ax_gyr.set_xlim(0, HISTORY)
ax_gyr.set_ylim(-60, 60)
ax_gyr.set_title("Gyroscope", color=TEXT, fontsize=9, pad=5)
ax_gyr.set_ylabel("°/s", color=DIM, fontsize=7.5)
ax_gyr.set_xlabel("Samples  (newest →)", color=DIM, fontsize=7.5)
ax_gyr.tick_params(colors=DIM, labelsize=6.5)
ax_gyr.set_xticks([])
ax_gyr.grid(True, alpha=0.08, color="white")
ax_gyr.axhline(0, color=BORDER, linewidth=0.7)
gyr_lines = [ax_gyr.plot([], [], color=c, linewidth=1.2, label=l)[0]
             for c, l in zip(GYR_CL, ["x", "y", "z"])]
ax_gyr.legend(loc="upper right", fontsize=7, labelcolor=TEXT,
              facecolor=PANEL, edgecolor=BORDER, ncol=3)


# ── Data panel ────────────────────────────────────────────────
# Static structure
ax_data.set_xlim(0, 1)
ax_data.set_ylim(0, 1)
kw   = dict(transform=ax_data.transAxes, family="monospace")
kw_s = dict(**kw, fontsize=7.5, color=TEXT)
kw_d = dict(**kw, fontsize=7.0, color=DIM)

def _t(x, y, s, **extra):
    return ax_data.text(x, y, s, **{**kw_s, **extra})

def _sep(y):
    ax_data.text(0.0, y, "─" * 29, **{**kw, "fontsize": 5.8, "color": BORDER})

_t(0.0, 0.975, "TOBII PRO GLASSES 2", fontweight="bold")
_sep(0.935)

_t(0.0, 0.900, "GAZE",              **kw_d, fontweight="bold")
_t(0.0, 0.858, "  2D",              **kw_d)
_t(0.0, 0.818, "  3D",              **kw_d)

_sep(0.785)
_t(0.0, 0.753, "LEFT EYE",  color=ORA, fontweight="bold")
_t(0.0, 0.713, "  diameter",        **kw_d)
_t(0.0, 0.673, "  Δ  L – R",        **kw_d)
_t(0.0, 0.633, "  center 3D",       **kw_d)
_t(0.0, 0.593, "  direction",       **kw_d)

_sep(0.560)
_t(0.0, 0.528, "RIGHT EYE", color=BLU, fontweight="bold")
_t(0.0, 0.488, "  diameter",        **kw_d)
_t(0.0, 0.448, "  center 3D",       **kw_d)
_t(0.0, 0.408, "  direction",       **kw_d)

_sep(0.375)
_t(0.0, 0.343, "VERGENCE",          **kw_d, fontweight="bold")
_t(0.0, 0.303, "  angle",           **kw_d)

_sep(0.270)
_t(0.0, 0.238, "HEAD",              **kw_d, fontweight="bold")
_t(0.0, 0.198, "  accel",           **kw_d)
_t(0.0, 0.158, "  gyro",            **kw_d)

_sep(0.125)
_t(0.0, 0.093, "SIGNAL",            **kw_d, fontweight="bold")
_t(0.0, 0.053, "  rate",            **kw_d)
_t(0.0, 0.013, "  quality",         **kw_d)

# Dynamic value text objects
X = 0.50
v_valid    = _t(X, 0.975, "● --")
v_gp2d     = _t(X, 0.858, "--")
v_gp3d     = _t(X, 0.818, "--", color=CYN)
v_pdL      = _t(X, 0.713, "--",  color=ORA)
v_delta    = _t(X, 0.673, "--",  color=DIM)
v_pcL      = _t(X, 0.633, "--",  color=DIM)
v_gdL      = _t(X, 0.593, "--",  color=DIM)
v_pdR      = _t(X, 0.488, "--",  color=BLU)
v_pcR      = _t(X, 0.448, "--",  color=DIM)
v_gdR      = _t(X, 0.408, "--",  color=DIM)
v_verg     = _t(X, 0.303, "--")
v_acc      = _t(X, 0.198, "--",  color=ACC_CL[1])
v_gyr      = _t(X, 0.158, "--",  color=GYR_CL[1])
v_rate     = _t(X, 0.053, "--")
v_quality  = _t(X, 0.013, "--")

x_hist = list(range(HISTORY))


# ── Animation ─────────────────────────────────────────────────
def update(_):
    L = latest
    v = L["valid"]

    # Gaze map
    xs, ys = list(gaze_xs), list(gaze_ys)
    gaze_trail.set_data(xs, ys)
    gaze_dot.set_data([xs[-1]], [ys[-1]])
    gaze_dot.set_color(TEXT if v else RED_C)
    gaze_dot.set_markeredgecolor(BLU if v else RED_C)
    gaze_status.set_text(
        f"{'● VALID' if v else '● LOST'}    "
        f"({xs[-1]:.3f},  {ys[-1]:.3f})"
    )
    gaze_status.set_color(GRN if v else RED_C)

    # Eyes
    for iris, pupil, hl, pdtxt, gd_k, pd_k in (
        (iris_L, pupil_L, hl_L, pdtxt_L, "gd_l", "pd_l"),
        (iris_R, pupil_R, hl_R, pdtxt_R, "gd_r", "pd_r"),
    ):
        ox, oy = gd_to_xy(L[gd_k])
        r = pd_to_r(L[pd_k])
        iris.set_center((ox, oy))
        pupil.set_center((ox, oy))
        pupil.set_radius(r)
        hl.set_center((ox + 0.10, oy + 0.15))
        pdtxt.set_text(f"pd  {L[pd_k]:.2f} mm")

    # Scrolling traces
    line_pdL.set_data(x_hist, list(pd_L))
    line_pdR.set_data(x_hist, list(pd_R))
    for i, ln in enumerate(acc_lines):
        ln.set_data(x_hist, list(acc_buf[i]))
    for i, ln in enumerate(gyr_lines):
        ln.set_data(x_hist, list(gyr_buf[i]))

    # Data panel values
    v_valid.set_text("● VALID" if v else "● LOST")
    v_valid.set_color(GRN if v else RED_C)

    v_gp2d.set_text(f"{L['gaze_x']:.3f}   {L['gaze_y']:.3f}")

    g3 = L["gp3"]
    v_gp3d.set_text(f"{g3[0]:.1f}  {g3[1]:.1f}  {g3[2]:.1f} mm")

    v_pdL.set_text(f"{L['pd_l']:.2f} mm")

    delta = L["pd_l"] - L["pd_r"]
    v_delta.set_text(f"{delta:+.2f} mm")
    v_delta.set_color(ORA if abs(delta) > 0.5 else DIM)

    pl = L["pc_l"]
    v_pcL.set_text(f"{pl[0]:.1f}  {pl[1]:.1f}  {pl[2]:.1f}")
    gl = L["gd_l"]
    v_gdL.set_text(f"{gl[0]:.3f}  {gl[1]:.3f}  {gl[2]:.3f}")

    v_pdR.set_text(f"{L['pd_r']:.2f} mm")
    pr = L["pc_r"]
    v_pcR.set_text(f"{pr[0]:.1f}  {pr[1]:.1f}  {pr[2]:.1f}")
    gr = L["gd_r"]
    v_gdR.set_text(f"{gr[0]:.3f}  {gr[1]:.3f}  {gr[2]:.3f}")

    vg = L["vergence"]
    dist = "far" if vg < 3 else ("near" if vg > 8 else "mid")
    v_verg.set_text(f"{vg:.1f}°   {dist}")

    a = L["acc"]
    v_acc.set_text(f"{a[0]:+.2f}  {a[1]:+.2f}  {a[2]:+.2f}")
    g = L["gyr"]
    v_gyr.set_text(f"{g[0]:+.2f}  {g[1]:+.2f}  {g[2]:+.2f}")

    v_rate.set_text(f"{L['sample_rate']:.1f} Hz")
    q = L["quality"]
    v_quality.set_text(f"{q:.1f} %")
    v_quality.set_color(GRN if q > 90 else (ORA if q > 70 else RED_C))

    return []

ani = animation.FuncAnimation(fig, update, interval=REFRESH_MS, blit=False)

plt.tight_layout()
try:
    plt.show()
finally:
    tobii.stop_streaming()
    print("[live_viz] Disconnected.")
