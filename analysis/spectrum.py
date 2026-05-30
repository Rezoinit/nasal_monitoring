# analysis/spectrum.py
# ─────────────────────────────────────────────────
# Power spectrum analysis of recorded nasal breathing data.
#
# Usage (CLI):
#   python analysis/spectrum.py <csv_file>
#   python analysis/spectrum.py calibration/raw_P01_1234567890.csv
#
# Usage (library):
#   from analysis.spectrum import compute_spectrum, plot_spectrum
#
# Input CSV must have columns: host_time, mic1, mic2
# (standard output from NasalMonitor or the calibration tool)
#
# Method: Welch's averaged periodogram.
# Reference:
#   Welch, P. D. (1967). The use of fast Fourier transform for the estimation
#   of power spectra: a method based on time averaging over short, modified
#   periodograms. IEEE Transactions on Audio and Electroacoustics, 15(2), 70–73.
#   https://doi.org/10.1109/TAU.1967.1161901
#
# Requires: numpy, scipy, matplotlib, pandas
#   pip install numpy scipy matplotlib pandas
# ─────────────────────────────────────────────────

import sys
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import signal


def compute_spectrum(
    csv_path: str,
    freq_min: float = 0.1,
    freq_max: float = 0.5,
    nperseg: Optional[int] = None,
) -> Dict[str, object]:
    """
    Load a CSV recording and compute Welch PSD for both mic channels.

    Parameters
    ----------
    csv_path : path to CSV file with columns host_time, mic1, mic2
    freq_min : lower edge of the breathing band in Hz  (default 0.1)
    freq_max : upper edge of the breathing band in Hz  (default 0.5)
    nperseg  : Welch segment length in samples.  None = min(512, N//4).

    Returns
    -------
    dict with keys:
        ``fs``           – estimated sample rate (Hz)
        ``n_samples``    – number of samples
        ``duration_s``   – recording duration (s)
        ``mic1_peak_hz`` – dominant breathing frequency for mic1 (Hz)
        ``mic1_peak_bpm``– dominant breathing rate for mic1 (bpm)
        ``mic2_peak_hz`` – dominant breathing frequency for mic2 (Hz)
        ``mic2_peak_bpm``– dominant breathing rate for mic2 (bpm)
        ``f``            – frequency axis array (shared by both channels)
        ``psd_mic1``     – PSD array for mic1
        ``psd_mic2``     – PSD array for mic2

    Reference
    ---------
    Welch, P. D. (1967). The use of fast Fourier transform for the estimation
    of power spectra: a method based on time averaging over short, modified
    periodograms. IEEE Transactions on Audio and Electroacoustics, 15(2), 70–73.
    https://doi.org/10.1109/TAU.1967.1161901
    """
    df = pd.read_csv(csv_path)

    for col in ("mic1", "mic2", "host_time"):
        if col not in df.columns:
            raise ValueError(
                f"CSV is missing required column '{col}'. "
                f"Found: {list(df.columns)}"
            )

    dt = df["host_time"].diff().median()
    fs = 1.0 / dt
    n  = len(df)

    seg = min(512, n // 4) if nperseg is None else nperseg
    seg = max(seg, 8)

    results: Dict[str, object] = {
        "fs": fs,
        "n_samples": n,
        "duration_s": n / fs,
    }

    mic_cfg = [
        ("mic1", "psd_mic1", "mic1_peak_hz", "mic1_peak_bpm"),
        ("mic2", "psd_mic2", "mic2_peak_hz", "mic2_peak_bpm"),
    ]

    f_shared = None
    for col, psd_key, hz_key, bpm_key in mic_cfg:
        f, psd = signal.welch(df[col], fs=fs, nperseg=seg)
        if f_shared is None:
            f_shared = f
            results["f"] = f
        results[psd_key] = psd

        mask = (f >= freq_min) & (f <= freq_max)
        if mask.any():
            peak_f = float(f[mask][np.argmax(psd[mask])])
        else:
            peak_f = float("nan")
        results[hz_key]  = peak_f
        results[bpm_key] = peak_f * 60.0

    return results


def plot_spectrum(
    csv_path: str,
    freq_min: float = 0.1,
    freq_max: float = 0.5,
    nperseg: Optional[int] = None,
    show: bool = True,
) -> None:
    """
    Compute and plot the power spectrum for both mic channels.

    Parameters mirror compute_spectrum().  Set show=False to get the figure
    without blocking (e.g. when saving to file in a batch script).
    """
    res = compute_spectrum(csv_path, freq_min=freq_min,
                           freq_max=freq_max, nperseg=nperseg)

    print(f"File         : {csv_path}")
    print(f"Samples      : {res['n_samples']}")
    print(f"Sample rate  : {res['fs']:.1f} Hz (estimated from timestamps)")
    print(f"Duration     : {res['duration_s']:.1f} s")
    print(f"mic1 dominant: {res['mic1_peak_hz']:.3f} Hz "
          f"({res['mic1_peak_bpm']:.1f} bpm)")
    print(f"mic2 dominant: {res['mic2_peak_hz']:.3f} Hz "
          f"({res['mic2_peak_bpm']:.1f} bpm)")

    fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    fig.suptitle(f"Power Spectrum — {csv_path.split('/')[-1]}", fontsize=13)

    mic_cfg = [
        ("psd_mic1", "#f5c842", "MIC1 — Yellow (left nostril)"),
        ("psd_mic2", "#4a90e2", "MIC2 — Blue  (right nostril)"),
    ]
    f = res["f"]
    for ax, (psd_key, color, label) in zip(axes, mic_cfg):
        psd = res[psd_key]
        ax.semilogy(f, psd, color=color, linewidth=1.5, label=label)
        ax.axvspan(freq_min, freq_max, alpha=0.08, color=color,
                   label=f"Breathing range ({freq_min}–{freq_max} Hz)")
        ax.set_ylabel("PSD (power/Hz)", fontsize=10)
        ax.set_xlim(0, min(res["fs"] / 2, 5))
        ax.legend(fontsize=9, loc="upper right")
        ax.grid(True, alpha=0.25)

    axes[-1].set_xlabel("Frequency (Hz)", fontsize=10)
    plt.tight_layout()
    if show:
        plt.show()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analysis/spectrum.py <csv_file> [freq_min] [freq_max]")
        sys.exit(1)
    _freq_min = float(sys.argv[2]) if len(sys.argv) > 2 else 0.1
    _freq_max = float(sys.argv[3]) if len(sys.argv) > 3 else 0.5
    plot_spectrum(sys.argv[1], freq_min=_freq_min, freq_max=_freq_max)
