# live_plot.py
# ─────────────────────────────────────────────────
# Real-time dashboard for the nasal sensor.
# Runs all analysis functions on a rolling window
# and updates plots live as data arrives.
#
# Usage:
#   python live_plot.py
#   python live_plot.py --port /dev/cu.usbmodem1101
#   python live_plot.py --hz 8 --window 30
# ─────────────────────────────────────────────────

import argparse
import collections
import threading
import time
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.animation import FuncAnimation

from nasal_monitor import NasalMonitor
from analysis import (
    bandpass_filter,
    normalize_signal,
    detect_breath_peaks,
    estimate_rate_psd,
    estimate_rate_peaks,
    nasal_asymmetry_index,
    bilateral_coherence,
    breathing_variability,
    instantaneous_rate,
    sample_entropy,
    detect_artifacts,
    classify_breathing_pattern,
)

# ─────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────

parser = argparse.ArgumentParser()
parser.add_argument("--port",   default=None,  help="Serial port (auto-detect if omitted)")
parser.add_argument("--hz",     type=float, default=8.0,  help="Downsampled rate (default 8)")
parser.add_argument("--window", type=float, default=30.0, help="Rolling analysis window in seconds (default 30)")
args = parser.parse_args()

FS         = args.hz
WINDOW_S   = args.window
WINDOW_N   = int(WINDOW_S * FS)   # samples in rolling window
UPDATE_MS  = 500                   # plot refresh interval

# ─────────────────────────────────────────────────
# SHARED RING BUFFERS  (thread-safe appends, numpy reads)
# ─────────────────────────────────────────────────

_lock   = threading.Lock()
mic1_buf = collections.deque(maxlen=WINDOW_N)
mic2_buf = collections.deque(maxlen=WINDOW_N)
time_buf = collections.deque(maxlen=WINDOW_N)

def on_reading(r):
    with _lock:
        mic1_buf.append(r.mic1)
        mic2_buf.append(r.mic2)
        time_buf.append(r.host_time)

monitor = NasalMonitor(
    port       = args.port,
    target_hz  = FS,
    live_detection = False,
)
monitor.on_reading(on_reading)

# ─────────────────────────────────────────────────
# FIGURE LAYOUT
# ─────────────────────────────────────────────────
# Row 0  — raw waveforms (mic1 + mic2)
# Row 1  — bandpass-filtered + detected peaks
# Row 2  — instantaneous breathing rate (bpm over time)
# Row 3  — PSD (left) | NAI trace (right)
# Row 4  — coherence (left) | text metrics panel (right)
# ─────────────────────────────────────────────────

fig = plt.figure(figsize=(16, 14))
fig.patch.set_facecolor("#0e0e14")
gs  = gridspec.GridSpec(5, 2, figure=fig,
                         hspace=0.55, wspace=0.35,
                         left=0.07, right=0.97, top=0.94, bottom=0.04)

AX_COLOR   = "#1a1a2e"
LINE_MIC1  = "#4fc3f7"   # cyan-blue  — left nostril
LINE_MIC2  = "#ef9a9a"   # rose       — right nostril
LINE_FILT  = "#80cbc4"   # teal       — filtered
LINE_RATE  = "#ffcc80"   # amber      — inst. rate
LINE_PSD   = "#ce93d8"   # purple
LINE_NAI   = "#a5d6a7"   # green
LINE_COH   = "#fff176"   # yellow
PEAK_COLOR = "#ff7043"   # orange-red

def _ax(row, col, title=""):
    ax = fig.add_subplot(gs[row, col])
    ax.set_facecolor(AX_COLOR)
    ax.tick_params(colors="#aaaaaa", labelsize=8)
    for spine in ax.spines.values():
        spine.set_edgecolor("#333355")
    if title:
        ax.set_title(title, color="#ddddee", fontsize=9, pad=4)
    return ax

ax_raw   = _ax(0, slice(0,2), "Raw ADC signal — mic1 (left, cyan) · mic2 (right, rose)")
ax_filt  = _ax(1, slice(0,2), "Bandpass-filtered (0.1–0.5 Hz) + detected peaks")
ax_rate  = _ax(2, slice(0,2), "Instantaneous breathing rate (bpm)")
ax_psd   = _ax(3, 0,          "Power Spectral Density — Welch")
ax_nai   = _ax(3, 1,          "Nasal Asymmetry Index (NAI %)")
ax_coh   = _ax(4, 0,          "Bilateral coherence")
ax_txt   = _ax(4, 1,          "Session metrics")

# static line handles (updated in-place each frame)
ln_m1,  = ax_raw.plot([], [], color=LINE_MIC1,  lw=1.0, label="mic1 left")
ln_m2,  = ax_raw.plot([], [], color=LINE_MIC2,  lw=1.0, label="mic2 right")
ln_f1,  = ax_filt.plot([], [], color=LINE_MIC1, lw=1.2, alpha=0.7)
ln_f2,  = ax_filt.plot([], [], color=LINE_MIC2, lw=1.2, alpha=0.7)
ln_ff,  = ax_filt.plot([], [], color=LINE_FILT, lw=1.6, label="mic1 filtered")
ln_pk,  = ax_filt.plot([], [], "o", color=PEAK_COLOR, ms=5, label="peaks")
ln_rate,= ax_rate.plot([], [], color=LINE_RATE, lw=1.5)
ln_psd, = ax_psd.plot([], [], color=LINE_PSD,  lw=1.4)
ln_nai, = ax_nai.plot([], [], color=LINE_NAI,  lw=1.2)
ln_coh, = ax_coh.plot([], [], color=LINE_COH,  lw=1.4)

ax_raw.legend(fontsize=7, facecolor="#111122", labelcolor="white", loc="upper right")
ax_filt.legend(fontsize=7, facecolor="#111122", labelcolor="white", loc="upper right")

ax_psd.set_xlabel("Frequency (Hz)", color="#aaaaaa", fontsize=7)
ax_psd.set_ylabel("PSD",            color="#aaaaaa", fontsize=7)
ax_nai.set_xlabel("Sample",         color="#aaaaaa", fontsize=7)
ax_nai.set_ylabel("NAI %",          color="#aaaaaa", fontsize=7)
ax_coh.set_xlabel("Frequency (Hz)", color="#aaaaaa", fontsize=7)
ax_coh.set_ylabel("Coherence",      color="#aaaaaa", fontsize=7)
ax_rate.set_ylabel("bpm",           color="#aaaaaa", fontsize=7)

for ax in (ax_raw, ax_filt, ax_rate, ax_psd, ax_nai, ax_coh):
    ax.grid(True, color="#222233", linewidth=0.5)

# NAI zero-line
ax_nai.axhline(0, color="#555566", lw=0.8, ls="--")
# Coherence threshold
ax_coh.axhline(0.5, color="#555566", lw=0.8, ls="--")

# ─────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────

MIN_SAMPLES = max(16, int(FS * 4))   # need at least 4 s to run any analysis

def _update_line(line, xdata, ydata):
    line.set_xdata(xdata)
    line.set_ydata(ydata)

def _rescale(ax, xdata=None, ydata=None, margin=0.05):
    if xdata is not None and len(xdata):
        ax.set_xlim(xdata[0], xdata[-1])
    if ydata is not None and len(ydata):
        lo, hi = np.nanmin(ydata), np.nanmax(ydata)
        span = hi - lo or 1.0
        ax.set_ylim(lo - margin * span, hi + margin * span)

# ─────────────────────────────────────────────────
# ANIMATION CALLBACK
# ─────────────────────────────────────────────────

def update(_frame):
    with _lock:
        m1 = np.array(mic1_buf, dtype=float)
        m2 = np.array(mic2_buf, dtype=float)

    n = len(m1)
    if n < MIN_SAMPLES:
        fig.suptitle(f"Collecting data… ({n}/{MIN_SAMPLES} samples)",
                     color="#ffcc80", fontsize=11)
        return

    t = np.arange(n) / FS   # relative time axis (seconds)

    # ── 1. Raw waveforms ──────────────────────────
    _update_line(ln_m1, t, m1)
    _update_line(ln_m2, t, m2)
    _rescale(ax_raw, t, np.concatenate([m1, m2]))

    # ── 2. Filtered + peaks ───────────────────────
    try:
        f1 = bandpass_filter(m1, FS)
        f2 = bandpass_filter(m2, FS)
        _update_line(ln_f1, t, f1)
        _update_line(ln_f2, t, f2)
        _update_line(ln_ff, t, f1)

        peaks = detect_breath_peaks(normalize_signal(f1), FS, method="ampd")
        if len(peaks):
            _update_line(ln_pk, t[peaks], f1[peaks])
        else:
            _update_line(ln_pk, [], [])
        _rescale(ax_filt, t, np.concatenate([f1, f2]))
    except Exception:
        peaks = np.array([], dtype=int)

    # ── 3. Instantaneous rate ─────────────────────
    try:
        if len(peaks) >= 2:
            t_rate, rate_bpm = instantaneous_rate(peaks, FS,
                                                   output_fs=FS,
                                                   total_samples=n)
            _update_line(ln_rate, t_rate / FS, rate_bpm)
            _rescale(ax_rate, t_rate / FS, rate_bpm)
        else:
            _update_line(ln_rate, [], [])
    except Exception:
        pass

    # ── 4. PSD ────────────────────────────────────
    try:
        psd_result = estimate_rate_psd(normalize_signal(f1), FS)
        freqs = psd_result["f"]
        power = psd_result["psd"]
        mask  = (freqs >= 0.05) & (freqs <= 1.0)
        _update_line(ln_psd, freqs[mask], power[mask])
        _rescale(ax_psd, freqs[mask], power[mask])
        ax_psd.axvline(psd_result["dominant_freq_hz"], color="#ff7043",
                       lw=1.0, ls="--", alpha=0.7)
        rate_psd = psd_result["rate_bpm"]
    except Exception:
        rate_psd = float("nan")

    # ── 5. NAI ────────────────────────────────────
    try:
        nai_result = nasal_asymmetry_index(m1, m2, window_s=5.0, fs=FS, step_s=1.0)
        nai_vals   = np.array(nai_result["nai_series"])
        _update_line(ln_nai, np.arange(len(nai_vals)), nai_vals)
        _rescale(ax_nai, np.arange(len(nai_vals)), nai_vals)
        nai_mean = float(np.mean(nai_vals))
        dominant_nostril = nai_result.get("dominance", "–")
    except Exception:
        nai_mean = float("nan")
        dominant_nostril = "–"

    # ── 6. Coherence ─────────────────────────────
    try:
        coh_result = bilateral_coherence(m1, m2, FS)
        coh_f  = np.array(coh_result["f"])
        coh_v  = np.array(coh_result["coherence"])
        mask_c = (coh_f >= 0.05) & (coh_f <= 1.0)
        _update_line(ln_coh, coh_f[mask_c], coh_v[mask_c])
        _rescale(ax_coh, coh_f[mask_c], None)
        ax_coh.set_ylim(0, 1.05)
        coh_mean = float(np.mean(coh_v[mask_c]))
    except Exception:
        coh_mean = float("nan")

    # ── 7. Breathing variability ──────────────────
    try:
        if len(peaks) >= 3:
            intervals = np.diff(peaks) / FS
            var_result = breathing_variability(intervals)
            sdbb  = var_result.get("sdbb_s", float("nan"))
            rmssd = var_result.get("rmssd_s", float("nan"))
            cv    = var_result.get("cv_percent", float("nan"))
        else:
            sdbb = rmssd = cv = float("nan")
    except Exception:
        sdbb = rmssd = cv = float("nan")

    # ── 8. Sample entropy ────────────────────────
    try:
        sampen = sample_entropy(normalize_signal(f1))
    except Exception:
        sampen = float("nan")

    # ── 9. Peak-based rate ───────────────────────
    try:
        pk_result  = estimate_rate_peaks(normalize_signal(f1), FS)
        rate_peaks = pk_result.get("rate_bpm", float("nan"))
    except Exception:
        rate_peaks = float("nan")

    # ── 10. Artifact check ───────────────────────
    try:
        art_result   = detect_artifacts(m1, m2, FS)
        any_artifact = art_result.get("any_artifact", False)
        art_flag     = "⚠ ARTIFACT" if any_artifact else "clean"
    except Exception:
        art_flag = "–"

    # ── 11. Pattern classification ────────────────
    try:
        rate_for_cls = rate_psd if not np.isnan(rate_psd) else rate_peaks
        cls_result   = classify_breathing_pattern(rate_for_cls)
        pattern      = cls_result.get("pattern", "–")
    except Exception:
        pattern = "–"

    # ── 12. Text panel ────────────────────────────
    ax_txt.cla()
    ax_txt.set_facecolor(AX_COLOR)
    ax_txt.set_title("Session metrics", color="#ddddee", fontsize=9, pad=4)
    ax_txt.axis("off")

    def _r(v, d=1):
        return f"{v:.{d}f}" if not (isinstance(v, float) and np.isnan(v)) else "–"

    rows = [
        ("Rate (PSD)",         f"{_r(rate_psd)} bpm"),
        ("Rate (peaks)",       f"{_r(rate_peaks)} bpm"),
        ("Pattern",            pattern),
        ("NAI mean",           f"{_r(nai_mean)} %"),
        ("Dominant nostril",   dominant_nostril),
        ("Coherence mean",     _r(coh_mean, 2)),
        ("SDBB",               f"{_r(sdbb, 3)} s"),
        ("RMSSD",              f"{_r(rmssd, 3)} s"),
        ("CV",                 f"{_r(cv, 1)} %"),
        ("Sample entropy",     _r(sampen, 3)),
        ("Peaks detected",     str(len(peaks))),
        ("Signal",             art_flag),
        ("Samples",            f"{n}  ({n/FS:.0f} s)"),
    ]

    for i, (label, value) in enumerate(rows):
        y = 1.0 - (i + 0.5) / len(rows)
        ax_txt.text(0.02, y, label + ":", transform=ax_txt.transAxes,
                    color="#aaaacc", fontsize=9, va="center")
        color = "#ff7043" if "ARTIFACT" in value else "#e8f5e9"
        ax_txt.text(0.55, y, value, transform=ax_txt.transAxes,
                    color=color, fontsize=9, va="center", fontweight="bold")

    fig.suptitle(
        f"Nasal Monitor — live  ·  {n/FS:.0f}s window  ·  {FS:.0f} Hz",
        color="#ccddff", fontsize=12
    )

# ─────────────────────────────────────────────────
# RUN
# ─────────────────────────────────────────────────

if __name__ == "__main__":
    monitor.start()
    ani = FuncAnimation(fig, update, interval=UPDATE_MS, cache_frame_data=False)
    plt.show()
    monitor.stop()