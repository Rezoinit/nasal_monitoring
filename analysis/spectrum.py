# analysis/spectrum.py
# ─────────────────────────────────────────────────
# Power spectrum analysis of recorded nasal breathing data.
#
# Usage:
#   python analysis/spectrum.py <csv_file>
#   python analysis/spectrum.py calibration/raw_P01_1234567890.csv
#
# Input CSV must have columns: host_time, mic1, mic2
# (standard output from NasalMonitor or the calibration tool)
#
# Requires: numpy, scipy, matplotlib, pandas
#   pip install numpy scipy matplotlib pandas
# ─────────────────────────────────────────────────

import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import signal


def compute_spectrum(csv_path: str):
    df = pd.read_csv(csv_path)

    if "mic1" not in df.columns or "mic2" not in df.columns:
        print(f"ERROR: CSV must have 'mic1' and 'mic2' columns.")
        print(f"  Found: {list(df.columns)}")
        sys.exit(1)

    # Estimate sample rate from host timestamps
    dt = df["host_time"].diff().median()
    fs = 1.0 / dt
    n  = len(df)
    print(f"File         : {csv_path}")
    print(f"Samples      : {n}")
    print(f"Sample rate  : {fs:.1f} Hz (estimated from timestamps)")
    print(f"Duration     : {n / fs:.1f} s")

    fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    fig.suptitle(f"Power Spectrum — {csv_path.split('/')[-1]}", fontsize=13)

    mic_cfg = [
        ("mic1", "#f5c842", "MIC1 — Yellow (left nostril)"),
        ("mic2", "#4a90e2", "MIC2 — Blue  (right nostril)"),
    ]

    for ax, (col, color, label) in zip(axes, mic_cfg):
        # Welch's method: better estimate than raw FFT for noisy signals
        nperseg = min(512, n // 4)
        f, psd  = signal.welch(df[col], fs=fs, nperseg=nperseg)

        # Breathing range: 0.1–0.5 Hz (6–30 breaths/min)
        breath_mask = (f >= 0.1) & (f <= 0.5)

        ax.semilogy(f, psd, color=color, linewidth=1.5, label=label)
        ax.axvspan(0.1, 0.5, alpha=0.08, color=color, label="Breathing range (0.1–0.5 Hz)")
        ax.set_ylabel("PSD (power/Hz)", fontsize=10)
        ax.set_xlim(0, min(fs / 2, 5))  # show up to 5 Hz
        ax.legend(fontsize=9, loc="upper right")
        ax.grid(True, alpha=0.25)

        # Print dominant frequency in breathing range
        if breath_mask.any():
            peak_f = f[breath_mask][np.argmax(psd[breath_mask])]
            print(f"{col} peak frequency: {peak_f:.3f} Hz "
                  f"({peak_f * 60:.1f} breaths/min)")

    axes[-1].set_xlabel("Frequency (Hz)", fontsize=10)
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python analysis/spectrum.py <csv_file>")
        sys.exit(1)
    compute_spectrum(sys.argv[1])
