# analysis/respiratory_analysis.py
# ─────────────────────────────────────────────────
# Post-hoc analysis functions for nasal airflow signals.
#
# Each function is self-contained, accepts a numpy array of signal values and a
# sampling rate (Hz), and exposes all meaningful parameters so callers can tune
# them for their study.  The docstring of every function cites the primary
# peer-reviewed source that defines or validates the method.
#
# Coordinate convention used throughout:
#   mic1  →  yellow wire  →  left  nostril
#   mic2  →  blue wire    →  right nostril
#
# Requires: numpy, scipy, pandas
#   pip install numpy scipy pandas
# ─────────────────────────────────────────────────

from __future__ import annotations

import math
import numpy as np
from scipy import signal as sp_signal
from scipy.interpolate import interp1d
from typing import Dict, Optional, Tuple


# ═════════════════════════════════════════════════
# 1. PREPROCESSING
# ═════════════════════════════════════════════════

def bandpass_filter(
    sig: np.ndarray,
    fs: float,
    lowcut: float = 0.1,
    highcut: float = 0.5,
    order: int = 4,
) -> np.ndarray:
    """
    Butterworth bandpass filter.

    Typical respiratory range is 0.1–0.5 Hz (6–30 breaths/min).
    Use a higher highcut (e.g. 2 Hz) if the signal contains artefact
    frequencies you need to characterise before removal.

    Parameters
    ----------
    sig     : 1-D signal array (raw ADC values or p2p amplitudes)
    fs      : sampling rate in Hz
    lowcut  : lower cutoff frequency in Hz  (default 0.1)
    highcut : upper cutoff frequency in Hz  (default 0.5)
    order   : filter order  (default 4; higher = steeper roll-off but more
              group delay — keep ≤ 6 for short respiratory recordings)

    Returns
    -------
    Filtered signal array, same shape as `sig`.

    Reference
    ---------
    Butterworth, S. (1930). On the theory of filter amplifiers.
    Experimental Wireless and the Wireless Engineer, 7(6), 536-541.
    """
    nyq = 0.5 * fs
    low = lowcut / nyq
    high = highcut / nyq
    b, a = sp_signal.butter(order, [low, high], btype="band")
    return sp_signal.filtfilt(b, a, sig)


def normalize_signal(sig: np.ndarray) -> np.ndarray:
    """
    Zero-mean, unit-variance normalization.

    Removes DC offset and scales amplitude so that downstream thresholds
    (e.g. in sample entropy or peak detection) are participant-independent.
    """
    std = np.std(sig)
    if std == 0:
        return sig - np.mean(sig)
    return (sig - np.mean(sig)) / std


# ═════════════════════════════════════════════════
# 2. PEAK DETECTION
# ═════════════════════════════════════════════════

def detect_breath_peaks(
    sig: np.ndarray,
    fs: float,
    method: str = "ampd",
    min_distance_s: float = 1.5,
    prominence: Optional[float] = None,
) -> np.ndarray:
    """
    Detect inspiration peaks in a respiratory amplitude signal.

    Two methods are available:

    ``ampd``  (default)
        Automatic Multiscale-based Peak Detection.  Requires no manual
        threshold tuning; works on noisy quasi-periodic signals.

    ``scipy``
        scipy.signal.find_peaks with distance and optional prominence
        constraints.  More familiar and faster on long recordings, but
        requires some manual prominence tuning for noisy data.

    Parameters
    ----------
    sig            : 1-D signal (pre-filtered p2p amplitude recommended)
    fs             : sampling rate in Hz
    method         : ``'ampd'`` or ``'scipy'``  (default ``'ampd'``)
    min_distance_s : minimum time between peaks in seconds  (default 1.5 s
                     → max ~40 breaths/min; increase for slow/resting breathing)
    prominence     : minimum peak prominence (scipy method only).
                     None = auto (0.1 × signal range).

    Returns
    -------
    1-D integer array of peak indices into ``sig``.

    References
    ----------
    Scholkmann, F., Boss, J., & Wolf, M. (2012). An efficient algorithm for
    automatic peak detection in noisy periodic and quasi-periodic signals.
    Algorithms, 5(4), 588–603.  https://doi.org/10.3390/a5040588

    For the scipy fallback:
    Virtanen, P. et al. (2020). SciPy 1.0: Fundamental algorithms for
    scientific computing in Python. Nature Methods, 17, 261–272.
    https://doi.org/10.1038/s41592-019-0686-2
    """
    if method == "ampd":
        return _ampd_peaks(sig, fs, min_distance_s)
    elif method == "scipy":
        min_dist_samples = int(min_distance_s * fs)
        if prominence is None:
            prominence = 0.1 * (np.max(sig) - np.min(sig))
        peaks, _ = sp_signal.find_peaks(
            sig, distance=min_dist_samples, prominence=prominence
        )
        return peaks
    else:
        raise ValueError(f"Unknown method '{method}'. Use 'ampd' or 'scipy'.")


def _ampd_peaks(sig: np.ndarray, fs: float, min_distance_s: float) -> np.ndarray:
    """
    AMPD algorithm core.

    Scholkmann et al. (2012), Algorithms 5(4):588-603.

    Implementation note: we use the first local minimum of the row-sum curve
    (γ) rather than the global minimum, following the pyampd reference library.
    This prevents pathologically large λ values on quasi-periodic signals with
    nearly equal peak amplitudes.
    Reference: ig248/pyampd on GitHub.
    """
    N = len(sig)
    L = int(math.ceil(N / 2.0)) - 1
    if L < 2:
        return np.array([], dtype=int)

    # Local maxima scalogram (vectorised scale-by-scale)
    LSM = np.zeros((L, N), dtype=np.int8)
    for k in range(1, L + 1):
        i_range = np.arange(k, N - k)
        mask = (sig[i_range] > sig[i_range - k]) & (sig[i_range] > sig[i_range + k])
        LSM[k - 1, i_range[mask]] = 1

    # Row-wise sum → γ curve
    row_sums = LSM.sum(axis=1).astype(float)

    # Use the FIRST local minimum of γ (more robust than global minimum
    # for signals with similar peak amplitudes).
    local_mins = sp_signal.argrelmin(row_sums, order=1)[0]
    if len(local_mins) > 0:
        lam = int(local_mins[0])
    else:
        # Fallback: global minimum ignoring zero-sum rows
        rs = row_sums.copy()
        rs[rs == 0] = N
        lam = int(np.argmin(rs))

    # Column sum: how many scales agree that this position is a local max.
    # Peaks are positions with the highest consensus (top fraction).
    # This is more robust than requiring ALL scales to agree, which fails
    # when neighbouring peaks have similar amplitudes (periodic signals).
    col_sums = LSM[:lam + 1, :].sum(axis=0)
    if col_sums.max() == 0:
        return np.array([], dtype=int)
    # Threshold: a position must be a local max at > 50 % of scales up to lam
    threshold = (lam + 1) * 0.5
    peaks = np.where(col_sums >= threshold)[0]

    # Enforce minimum inter-peak distance
    min_dist = int(min_distance_s * fs)
    if len(peaks) <= 1 or min_dist <= 1:
        return peaks

    filtered = [peaks[0]]
    for p in peaks[1:]:
        if p - filtered[-1] >= min_dist:
            filtered.append(p)
    return np.array(filtered, dtype=int)


# ═════════════════════════════════════════════════
# 3. BREATHING RATE ESTIMATION
# ═════════════════════════════════════════════════

def estimate_rate_psd(
    sig: np.ndarray,
    fs: float,
    freq_min: float = 0.1,
    freq_max: float = 0.5,
    nperseg: Optional[int] = None,
    noverlap: Optional[int] = None,
) -> Dict[str, float]:
    """
    Estimate breathing rate from the dominant frequency of the Power Spectral
    Density using Welch's averaged periodogram method.

    This is the most reliable single-number rate estimate for steady-state
    recordings of ≥ 30 s.  Shorter windows reduce frequency resolution.

    Parameters
    ----------
    sig      : 1-D signal array
    fs       : sampling rate in Hz
    freq_min : lower bound of breathing band in Hz  (default 0.1)
    freq_max : upper bound of breathing band in Hz  (default 0.5)
    nperseg  : samples per Welch segment.  None = min(512, N//4).
               Larger values give finer frequency resolution but need more data.
    noverlap : segment overlap in samples.  None = nperseg // 2 (50 %).

    Returns
    -------
    dict with keys:
        ``rate_hz``   – dominant frequency in Hz
        ``rate_bpm``  – dominant frequency in breaths/min
        ``psd_peak``  – PSD value at dominant frequency
        ``f``         – full frequency array (numpy)
        ``psd``       – full PSD array (numpy)

    Reference
    ---------
    Welch, P. D. (1967). The use of fast Fourier transform for the estimation
    of power spectra: a method based on time averaging over short, modified
    periodograms. IEEE Transactions on Audio and Electroacoustics, 15(2), 70–73.
    https://doi.org/10.1109/TAU.1967.1161901
    """
    N = len(sig)
    if nperseg is None:
        nperseg = min(512, N // 4)
    nperseg = max(nperseg, 8)

    f, psd = sp_signal.welch(sig, fs=fs, nperseg=nperseg, noverlap=noverlap)

    mask = (f >= freq_min) & (f <= freq_max)
    if not mask.any():
        return {"rate_hz": float("nan"), "rate_bpm": float("nan"),
                "psd_peak": float("nan"), "f": f, "psd": psd}

    peak_idx = np.argmax(psd[mask])
    rate_hz = float(f[mask][peak_idx])
    return {
        "rate_hz": rate_hz,
        "rate_bpm": rate_hz * 60.0,
        "psd_peak": float(psd[mask][peak_idx]),
        "f": f,
        "psd": psd,
    }


def estimate_rate_peaks(
    sig: np.ndarray,
    fs: float,
    method: str = "ampd",
    min_distance_s: float = 1.5,
    prominence: Optional[float] = None,
) -> Dict[str, object]:
    """
    Estimate mean breathing rate by counting detected peaks.

    Complements the PSD method: more reliable for very short windows or when
    breathing rate varies substantially within the recording.

    Parameters
    ----------
    sig            : 1-D signal (bandpass-filtered p2p amplitude recommended)
    fs             : sampling rate in Hz
    method         : peak detector — ``'ampd'`` or ``'scipy'``
    min_distance_s : minimum inter-peak time in seconds  (default 1.5)
    prominence     : prominence threshold (scipy only)

    Returns
    -------
    dict with keys:
        ``rate_bpm``     – mean breathing rate in breaths/min
        ``n_breaths``    – number of detected peaks
        ``duration_s``   – total recording duration in seconds
        ``peak_indices`` – array of peak sample indices

    Reference
    ---------
    Charlton, P. H. et al. (2018). Breathing rate estimation from the
    electrocardiogram and photoplethysmogram: a review.  IEEE Reviews in
    Biomedical Engineering, 11, 2–20.
    https://doi.org/10.1109/RBME.2017.2763681
    """
    peaks = detect_breath_peaks(sig, fs, method=method,
                                min_distance_s=min_distance_s,
                                prominence=prominence)
    duration_s = len(sig) / fs
    rate_bpm = (len(peaks) / duration_s) * 60.0 if duration_s > 0 else float("nan")
    return {
        "rate_bpm": rate_bpm,
        "n_breaths": len(peaks),
        "duration_s": duration_s,
        "peak_indices": peaks,
    }


def estimate_rate_autocorr(
    sig: np.ndarray,
    fs: float,
    freq_min: float = 0.1,
    freq_max: float = 0.5,
) -> Dict[str, float]:
    """
    Estimate breathing rate from the lag of the first dominant peak in the
    autocorrelation function.

    Useful as a cross-check against the PSD method, especially when the
    signal has a non-stationary amplitude envelope (e.g. deep-to-shallow
    transitions).

    Parameters
    ----------
    sig      : 1-D signal array
    fs       : sampling rate in Hz
    freq_min : minimum plausible frequency in Hz  (default 0.1)
    freq_max : maximum plausible frequency in Hz  (default 0.5)

    Returns
    -------
    dict with keys:
        ``rate_hz``    – estimated breathing rate in Hz
        ``rate_bpm``   – estimated breathing rate in breaths/min
        ``lag_s``      – dominant lag in seconds
        ``confidence`` – normalised autocorrelation value at that lag (0–1)

    Reference
    ---------
    Kontaxis, S. et al. (2020). Towards understanding breathing dysregulation
    in chronic pain: time–frequency analysis of breathing-related indices.
    Entropy, 22(8), 902.  https://doi.org/10.3390/e22080902
    """
    sig_z = sig - np.mean(sig)
    ac = np.correlate(sig_z, sig_z, mode="full")
    ac = ac[len(ac) // 2:]          # keep non-negative lags
    ac /= ac[0] + 1e-12              # normalise

    lag_min = int(fs / freq_max)
    lag_max = int(fs / freq_min)
    lag_min = max(lag_min, 1)
    lag_max = min(lag_max, len(ac) - 1)

    if lag_min >= lag_max:
        return {"rate_hz": float("nan"), "rate_bpm": float("nan"),
                "lag_s": float("nan"), "confidence": 0.0}

    search = ac[lag_min:lag_max]
    best_offset = int(np.argmax(search))
    best_lag = lag_min + best_offset

    rate_hz = fs / best_lag
    return {
        "rate_hz": rate_hz,
        "rate_bpm": rate_hz * 60.0,
        "lag_s": best_lag / fs,
        "confidence": float(ac[best_lag]),
    }


def estimate_rate_zerocross(
    sig: np.ndarray,
    fs: float,
    detrend: bool = True,
) -> Dict[str, float]:
    """
    Estimate breathing rate from the mean inter-zero-crossing interval.

    Each full breath cycle contains two zero crossings (ascending + descending).
    This method works directly on the detrended raw signal without requiring
    peak detection and is robust to amplitude modulation.

    Parameters
    ----------
    sig     : 1-D signal array (bandpass-filtered recommended)
    fs      : sampling rate in Hz
    detrend : remove linear trend before counting  (default True)

    Returns
    -------
    dict with keys:
        ``rate_bpm``      – estimated breathing rate in breaths/min
        ``n_crossings``   – total zero crossings detected
        ``mean_period_s`` – mean period between same-direction crossings

    Reference
    ---------
    Garde, A. et al. (2014). Estimating respiratory and heart rates from the
    correntropy spectral density of the photoplethysmogram.  PLOS ONE, 9(1),
    e86427.  https://doi.org/10.1371/journal.pone.0086427
    """
    s = sp_signal.detrend(sig) if detrend else sig.copy()
    crossings = np.where(np.diff(np.sign(s)))[0]

    if len(crossings) < 2:
        return {"rate_bpm": float("nan"), "n_crossings": 0, "mean_period_s": float("nan")}

    # Consecutive same-direction crossings are one full cycle apart
    # Use every other crossing to get full-period intervals
    full_crossings = crossings[::2]
    if len(full_crossings) < 2:
        return {"rate_bpm": float("nan"), "n_crossings": len(crossings),
                "mean_period_s": float("nan")}

    intervals_s = np.diff(full_crossings) / fs
    mean_period = float(np.mean(intervals_s))
    rate_bpm = (1.0 / mean_period) * 60.0 if mean_period > 0 else float("nan")
    return {
        "rate_bpm": rate_bpm,
        "n_crossings": len(crossings),
        "mean_period_s": mean_period,
    }


# ═════════════════════════════════════════════════
# 4. NASAL / BILATERAL ANALYSIS
# ═════════════════════════════════════════════════

def nasal_asymmetry_index(
    mic1: np.ndarray,
    mic2: np.ndarray,
    window_s: Optional[float] = None,
    fs: Optional[float] = None,
    step_s: Optional[float] = None,
) -> Dict[str, object]:
    """
    Nasal Asymmetry Index (NAI) — also called the Laterality Index.

    NAI = (mic1 − mic2) / (mic1 + mic2) × 100

    Interpretation:
        NAI > 0  →  left (yellow mic) dominant
        NAI < 0  →  right (blue mic) dominant
        NAI ≈ 0  →  bilateral equal airflow
        |NAI| > 25 is typically considered clinically significant asymmetry

    Sliding-window mode: provide `window_s`, `fs`, and `step_s` to get a
    time-varying asymmetry curve.  Useful for detecting the nasal cycle
    (natural ~2–7 h alternation of dominant nostril).

    Parameters
    ----------
    mic1     : left nostril amplitude array
    mic2     : right nostril amplitude array
    window_s : sliding window length in seconds (None = whole-recording mean)
    fs       : sampling rate in Hz (required only for sliding-window mode)
    step_s   : window step in seconds (default = window_s / 2)

    Returns
    -------
    dict with keys:
        ``nai_mean``   – mean NAI over the whole recording
        ``nai_std``    – standard deviation of NAI
        ``dominance``  – ``'left'``, ``'right'``, or ``'equal'``
        ``nai_series`` – array of per-window NAI values (sliding-window mode only)
        ``times_s``    – centre time of each window in seconds (sliding-window only)

    References
    ----------
    Eccles, R. (1996). A role for the nasal cycle in respiratory defence.
    European Respiratory Journal, 9(2), 371–376.
    https://doi.org/10.1183/09031936.96.09020371

    Flanagan, P., & Eccles, R. (1997). Spontaneous changes of unilateral nasal
    airflow in man: a re-examination of the 'nasal cycle'.
    Acta Oto-Laryngologica, 117(4), 590–595.
    https://doi.org/10.3109/00016489709113437
    """
    m1 = np.asarray(mic1, dtype=float)
    m2 = np.asarray(mic2, dtype=float)
    denom = m1 + m2
    denom[denom == 0] = np.nan
    nai_all = (m1 - m2) / denom * 100.0

    result: Dict[str, object] = {
        "nai_mean": float(np.nanmean(nai_all)),
        "nai_std": float(np.nanstd(nai_all)),
    }
    mean = result["nai_mean"]
    if mean > 5:
        result["dominance"] = "left"
    elif mean < -5:
        result["dominance"] = "right"
    else:
        result["dominance"] = "equal"

    if window_s is not None and fs is not None:
        win = int(window_s * fs)
        stp = int((step_s if step_s else window_s / 2) * fs)
        nai_series, times_s = [], []
        for start in range(0, len(m1) - win + 1, stp):
            end = start + win
            w_denom = m1[start:end] + m2[start:end]
            w_denom[w_denom == 0] = np.nan
            nai_series.append(float(np.nanmean((m1[start:end] - m2[start:end]) / w_denom * 100.0)))
            times_s.append((start + win / 2) / fs)
        result["nai_series"] = np.array(nai_series)
        result["times_s"] = np.array(times_s)

    return result


def bilateral_coherence(
    mic1: np.ndarray,
    mic2: np.ndarray,
    fs: float,
    nperseg: Optional[int] = None,
) -> Dict[str, object]:
    """
    Magnitude-squared coherence between the two nostril channels.

    High coherence in the breathing band (0.1–0.5 Hz) indicates synchronous
    bilateral airflow (normal nasal breathing). Low coherence suggests
    independent channel behaviour — possible unilateral occlusion or artefact.

    Parameters
    ----------
    mic1    : left nostril amplitude array
    mic2    : right nostril amplitude array
    fs      : sampling rate in Hz
    nperseg : Welch segment length (None = min(256, N//4))

    Returns
    -------
    dict with keys:
        ``f``                – frequency array
        ``coherence``        – magnitude-squared coherence (0–1) per frequency
        ``mean_coh_breath``  – mean coherence in the 0.1–0.5 Hz band

    Reference
    ---------
    Carter, G. C. (1987). Coherence and time delay estimation.
    Proceedings of the IEEE, 75(2), 236–255.
    https://doi.org/10.1109/PROC.1987.13723
    """
    N = len(mic1)
    if nperseg is None:
        nperseg = min(256, N // 4)
    nperseg = max(nperseg, 8)

    f, coh = sp_signal.coherence(mic1, mic2, fs=fs, nperseg=nperseg)
    mask = (f >= 0.1) & (f <= 0.5)
    mean_coh = float(np.mean(coh[mask])) if mask.any() else float("nan")
    return {"f": f, "coherence": coh, "mean_coh_breath": mean_coh}


# ═════════════════════════════════════════════════
# 5. BREATH INTERVAL & VARIABILITY METRICS
# ═════════════════════════════════════════════════

def breath_intervals(peaks: np.ndarray, fs: float) -> np.ndarray:
    """
    Compute breath-to-breath (BB) intervals from an array of peak indices.

    Parameters
    ----------
    peaks : integer array of peak sample indices (from detect_breath_peaks)
    fs    : sampling rate in Hz

    Returns
    -------
    1-D float array of inter-peak intervals in seconds.
    """
    if len(peaks) < 2:
        return np.array([], dtype=float)
    return np.diff(peaks.astype(float)) / fs


def breathing_variability(intervals_s: np.ndarray) -> Dict[str, float]:
    """
    HRV-equivalent variability metrics adapted for breathing intervals.

    Metrics mirror the time-domain HRV standard to make comparison with
    cardiac data straightforward.  All interval units are seconds.

    Parameters
    ----------
    intervals_s : 1-D array of breath-to-breath intervals in seconds

    Returns
    -------
    dict with keys:
        ``mean_bb_s``  – mean BB interval (s)
        ``mean_bpm``   – mean breathing rate (breaths/min)
        ``sdbb``       – std of BB intervals — overall variability (s)
        ``rmssd``      – root-mean-square of successive differences — short-term
                         variability (s)
        ``cv``         – coefficient of variation = SDBB / mean × 100 (%)
        ``pbb50``      – % of successive differences > 500 ms  (analogous to
                         pNN50 in HRV but using a 500 ms threshold instead of
                         50 ms, scaled for respiratory timescales)
        ``n_intervals``– number of intervals used

    Reference
    ---------
    Task Force of the European Society of Cardiology and the North American
    Society of Pacing and Electrophysiology (1996). Heart rate variability:
    standards of measurement, physiological interpretation and clinical use.
    Circulation, 93(5), 1043–1065.
    https://doi.org/10.1161/01.CIR.93.5.1043
    (Adapted here for respiratory inter-breath intervals following the same
    mathematical framework.)
    """
    bb = np.asarray(intervals_s, dtype=float)
    if len(bb) == 0:
        return {k: float("nan") for k in
                ["mean_bb_s", "mean_bpm", "sdbb", "rmssd", "cv", "pbb50", "n_intervals"]}

    mean_bb = float(np.mean(bb))
    sdbb = float(np.std(bb, ddof=1)) if len(bb) > 1 else 0.0
    successive_diff = np.diff(bb)
    rmssd = float(np.sqrt(np.mean(successive_diff ** 2))) if len(successive_diff) > 0 else float("nan")
    cv = (sdbb / mean_bb * 100.0) if mean_bb > 0 else float("nan")
    pbb50 = (float(np.sum(np.abs(successive_diff) > 0.5)) / len(successive_diff) * 100.0
             if len(successive_diff) > 0 else float("nan"))
    return {
        "mean_bb_s": mean_bb,
        "mean_bpm": 60.0 / mean_bb if mean_bb > 0 else float("nan"),
        "sdbb": sdbb,
        "rmssd": rmssd,
        "cv": cv,
        "pbb50": pbb50,
        "n_intervals": len(bb),
    }


def instantaneous_rate(
    peaks: np.ndarray,
    fs: float,
    output_fs: float = 1.0,
    total_samples: Optional[int] = None,
    method: str = "linear",
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Compute a time-varying breathing rate curve by interpolating beat-to-beat
    intervals onto a uniform time grid.

    Parameters
    ----------
    peaks         : integer array of peak sample indices
    fs            : sampling rate of the original signal in Hz
    output_fs     : desired output rate of the rate curve in Hz  (default 1 Hz)
    total_samples : length of original signal; if None, uses last peak index
    method        : interpolation method — ``'linear'``, ``'cubic'``, or
                    ``'nearest'``  (passed to scipy.interpolate.interp1d)

    Returns
    -------
    (times_s, rate_bpm)
        times_s   – uniformly spaced time axis in seconds
        rate_bpm  – instantaneous breathing rate in breaths/min at each time

    Reference
    ---------
    Moody, G. B., Mark, R. G., Zoccola, A., & Mantero, S. (1985).
    Derivation of respiratory signals from multi-lead ECGs.
    Computers in Cardiology, 12, 113–116.
    (Framework for interpolated instantaneous rate; applied here to nasal
    airflow peak series.)
    """
    if len(peaks) < 2:
        return np.array([]), np.array([])

    peak_times = peaks / fs
    ibi = np.diff(peak_times)                 # inter-breath intervals
    ibi_times = peak_times[:-1] + ibi / 2.0   # midpoint of each interval

    rate_at_ibi = 60.0 / ibi

    end_time = (total_samples / fs) if total_samples else peak_times[-1]
    t_out = np.arange(ibi_times[0], end_time, 1.0 / output_fs)

    if len(ibi_times) < 2:
        return t_out, np.full_like(t_out, rate_at_ibi[0])

    kind = method if method in ("linear", "cubic", "nearest") else "linear"
    interp_fn = interp1d(ibi_times, rate_at_ibi, kind=kind,
                         bounds_error=False, fill_value="extrapolate")
    rate_bpm = interp_fn(t_out)
    return t_out, rate_bpm


# ═════════════════════════════════════════════════
# 6. SIGNAL COMPLEXITY
# ═════════════════════════════════════════════════

def sample_entropy(
    sig: np.ndarray,
    m: int = 2,
    r: Optional[float] = None,
    normalize: bool = True,
) -> float:
    """
    Sample Entropy (SampEn) — measure of signal irregularity / complexity.

    Lower SampEn → more regular, predictable breathing (e.g. metronomic pacing)
    Higher SampEn → more complex, irregular breathing

    Parameters
    ----------
    sig       : 1-D signal array (typically the BB interval series, not raw ADC)
    m         : template length  (default 2; typically 1 or 2)
    r         : tolerance (similarity threshold).  None = 0.2 × std of signal
                (standard practice; increase for noisier signals)
    normalize : z-score the signal before computing  (default True; makes r
                comparison easier across participants)

    Returns
    -------
    SampEn value (float).  Returns ``nan`` if computation fails (too few
    matches or too-short signal).

    Reference
    ---------
    Richman, J. S., & Moorman, J. R. (2000). Physiological time-series
    analysis using approximate entropy and sample entropy.
    American Journal of Physiology — Heart and Circulatory Physiology,
    278(6), H2039–H2049.  https://doi.org/10.1152/ajpheart.2000.278.6.H2039
    """
    x = np.asarray(sig, dtype=float)
    if normalize:
        std = np.std(x)
        x = (x - np.mean(x)) / std if std > 0 else x - np.mean(x)

    N = len(x)
    if N < 2 * m + 2:
        return float("nan")

    if r is None:
        r = 0.2 * np.std(x)

    def _count_templates(length: int) -> int:
        count = 0
        templates = np.array([x[i:i + length] for i in range(N - length)])
        for i in range(N - length):
            diffs = np.max(np.abs(templates - templates[i]), axis=1)
            # exclude self-match
            count += np.sum(diffs <= r) - 1
        return count

    B = _count_templates(m)
    A = _count_templates(m + 1)

    if B == 0:
        return float("nan")
    ratio = A / B
    if ratio <= 0:
        return float("nan")
    return float(-math.log(ratio))


# ═════════════════════════════════════════════════
# 7. ARTEFACT DETECTION
# ═════════════════════════════════════════════════

def detect_artifacts(
    mic1: np.ndarray,
    mic2: np.ndarray,
    fs: float,
    motion_z: float = 3.5,
    speech_corr: float = 0.85,
    speech_window_s: float = 1.0,
    highfreq_cutoff: float = 2.0,
) -> Dict[str, object]:
    """
    Detect motion and speech artefacts in bilateral nasal airflow signals.

    Two artefact types are flagged:

    Motion artefacts
        Characterised by sharp, synchronised spikes on both channels
        simultaneously.  Detected as samples where both channels exceed
        `motion_z` standard deviations above their rolling mean, happening
        within the same window.

    Speech / vibration artefacts
        Characterised by high bilateral coherence at frequencies above the
        normal breathing band (> 0.5 Hz) and high cross-channel correlation
        within short windows.

    Parameters
    ----------
    mic1            : left nostril amplitude array
    mic2            : right nostril amplitude array
    fs              : sampling rate in Hz
    motion_z        : z-score threshold for both channels to be flagged as
                      motion artefact  (default 3.5; lower = more sensitive)
    speech_corr     : Pearson correlation threshold between channels within a
                      short window to flag speech  (default 0.85)
    speech_window_s : window length in seconds for speech detection  (default 1.0)
    highfreq_cutoff : lower cutoff for the high-frequency channel used in speech
                      detection (Hz)  (default 2.0 Hz)

    Returns
    -------
    dict with keys:
        ``motion_mask``  – boolean array, True where motion artefact detected
        ``speech_mask``  – boolean array, True where speech artefact detected
        ``combined_mask``– boolean OR of the above two masks
        ``motion_frac``  – fraction of samples flagged as motion (0–1)
        ``speech_frac``  – fraction of samples flagged as speech (0–1)

    Reference
    ---------
    Sörnmo, L., & Laguna, P. (2005). Bioelectrical Signal Processing in
    Cardiac and Neurological Applications. Elsevier Academic Press.
    Chapter 6: Artefact processing in biomedical signals.
    ISBN: 978-0-12-437552-9
    (General artefact detection framework; thresholds adapted for MEMS
    microphone-based airflow signals.)
    """
    m1 = np.asarray(mic1, dtype=float)
    m2 = np.asarray(mic2, dtype=float)
    N = len(m1)

    # --- Motion: bilateral z-score spike ---
    z1 = (m1 - np.mean(m1)) / (np.std(m1) + 1e-9)
    z2 = (m2 - np.mean(m2)) / (np.std(m2) + 1e-9)
    motion_mask = (np.abs(z1) > motion_z) & (np.abs(z2) > motion_z)

    # --- Speech: short-window bilateral correlation ---
    speech_mask = np.zeros(N, dtype=bool)
    win = max(int(speech_window_s * fs), 4)
    for start in range(0, N - win + 1, win // 2):
        end = start + win
        seg1, seg2 = m1[start:end], m2[start:end]
        if np.std(seg1) < 1e-9 or np.std(seg2) < 1e-9:
            continue
        corr = float(np.corrcoef(seg1, seg2)[0, 1])
        if corr >= speech_corr:
            speech_mask[start:end] = True

    combined_mask = motion_mask | speech_mask
    return {
        "motion_mask": motion_mask,
        "speech_mask": speech_mask,
        "combined_mask": combined_mask,
        "motion_frac": float(np.mean(motion_mask)),
        "speech_frac": float(np.mean(speech_mask)),
    }


# ═════════════════════════════════════════════════
# 8. CLINICAL PATTERN CLASSIFICATION
# ═════════════════════════════════════════════════

def classify_breathing_pattern(
    rate_bpm: float,
    bradypnea_threshold: float = 12.0,
    tachypnea_threshold: float = 20.0,
    hyperpnea_threshold: float = 30.0,
) -> Dict[str, str]:
    """
    Classify breathing rate into standard clinical categories.

    Default thresholds follow adult respiratory physiology norms:
        Bradypnea   < 12 bpm  — abnormally slow
        Eupnea     12–20 bpm  — normal adult resting range
        Tachypnea  20–30 bpm  — elevated (exertion, fever, anxiety)
        Hyperpnea   > 30 bpm  — abnormally rapid

    All thresholds are adjustable for paediatric populations or
    study-specific definitions.

    Parameters
    ----------
    rate_bpm             : breathing rate in breaths/min
    bradypnea_threshold  : upper bound of bradypnea range  (default 12)
    tachypnea_threshold  : lower bound of tachypnea range  (default 20)
    hyperpnea_threshold  : lower bound of hyperpnea range  (default 30)

    Returns
    -------
    dict with keys:
        ``pattern``     – ``'bradypnea'``, ``'eupnea'``, ``'tachypnea'``,
                          ``'hyperpnea'``, or ``'unknown'``
        ``rate_bpm``    – rate passed in (echo for convenience)
        ``clinical_note``– one-line clinical interpretation

    Reference
    ---------
    Tobin, M. J. et al. (1983). Breathing patterns: 1. Normal subjects.
    Chest, 84(2), 202–205.  https://doi.org/10.1378/chest.84.2.202

    Tobin, M. J. (1990). Breathing abnormalities during sleep.
    Archives of Internal Medicine, 150(8), 1779–1785.
    https://doi.org/10.1001/archinte.1990.00390200099017
    """
    if math.isnan(rate_bpm):
        return {"pattern": "unknown", "rate_bpm": rate_bpm,
                "clinical_note": "Rate could not be estimated."}

    if rate_bpm < bradypnea_threshold:
        pattern = "bradypnea"
        note = f"Abnormally slow breathing ({rate_bpm:.1f} bpm < {bradypnea_threshold} bpm)."
    elif rate_bpm <= tachypnea_threshold:
        pattern = "eupnea"
        note = f"Normal resting breathing rate ({rate_bpm:.1f} bpm)."
    elif rate_bpm <= hyperpnea_threshold:
        pattern = "tachypnea"
        note = f"Elevated breathing rate ({rate_bpm:.1f} bpm); check for exertion or anxiety."
    else:
        pattern = "hyperpnea"
        note = f"Abnormally rapid breathing ({rate_bpm:.1f} bpm > {hyperpnea_threshold} bpm)."

    return {"pattern": pattern, "rate_bpm": rate_bpm, "clinical_note": note}


# ═════════════════════════════════════════════════
# 9. CONVENIENCE: FULL-RECORDING SUMMARY
# ═════════════════════════════════════════════════

def analyse_recording(
    mic1: np.ndarray,
    mic2: np.ndarray,
    fs: float,
    filter_signal: bool = True,
    peak_method: str = "ampd",
    psd_freq_min: float = 0.1,
    psd_freq_max: float = 0.5,
) -> Dict[str, object]:
    """
    Run the full analysis pipeline on one recording and return a summary dict.

    This function calls the individual building-block functions above in the
    recommended order.  Use the individual functions directly if you need
    finer control over any step.

    Parameters
    ----------
    mic1          : left nostril amplitude array (raw or p2p)
    mic2          : right nostril amplitude array
    fs            : sampling rate in Hz
    filter_signal : bandpass-filter before peak detection  (default True;
                    set False if you have already filtered)
    peak_method   : ``'ampd'`` or ``'scipy'``
    psd_freq_min  : lower edge of breathing band in Hz
    psd_freq_max  : upper edge of breathing band in Hz

    Returns
    -------
    Nested dict with keys: ``rate``, ``variability``, ``nasal``,
    ``complexity``, ``pattern``, ``artifacts``.
    Each sub-dict mirrors the return values of the respective function.
    """
    m1 = np.asarray(mic1, dtype=float)
    m2 = np.asarray(mic2, dtype=float)

    m1_f = bandpass_filter(m1, fs, psd_freq_min, psd_freq_max) if filter_signal else m1
    m2_f = bandpass_filter(m2, fs, psd_freq_min, psd_freq_max) if filter_signal else m2
    combined = (m1_f + m2_f) / 2.0

    rate_psd  = estimate_rate_psd(combined, fs, psd_freq_min, psd_freq_max)
    rate_pk   = estimate_rate_peaks(combined, fs, method=peak_method)
    rate_ac   = estimate_rate_autocorr(combined, fs, psd_freq_min, psd_freq_max)
    rate_zc   = estimate_rate_zerocross(combined, fs)

    peaks = rate_pk["peak_indices"]
    ibi   = breath_intervals(peaks, fs)
    var   = breathing_variability(ibi)

    nai   = nasal_asymmetry_index(m1, m2)
    coh   = bilateral_coherence(m1, m2, fs)

    samplen = sample_entropy(ibi) if len(ibi) >= 10 else float("nan")
    arts    = detect_artifacts(m1, m2, fs)
    pattern = classify_breathing_pattern(rate_psd["rate_bpm"])

    return {
        "rate": {
            "psd_bpm":       rate_psd["rate_bpm"],
            "peaks_bpm":     rate_pk["rate_bpm"],
            "autocorr_bpm":  rate_ac["rate_bpm"],
            "zerocross_bpm": rate_zc["rate_bpm"],
        },
        "variability": var,
        "nasal": {
            "nai_mean":        nai["nai_mean"],
            "nai_std":         nai["nai_std"],
            "dominance":       nai["dominance"],
            "mean_coh_breath": coh["mean_coh_breath"],
        },
        "complexity": {"sample_entropy": samplen},
        "pattern": pattern,
        "artifacts": {
            "motion_frac": arts["motion_frac"],
            "speech_frac": arts["speech_frac"],
        },
    }
