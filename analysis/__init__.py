# analysis/__init__.py
# Make analysis/ importable as a package.
# Import the most commonly used functions at the top level.

from .respiratory_analysis import (
    # Preprocessing
    bandpass_filter,
    normalize_signal,
    # Peak detection
    detect_breath_peaks,
    # Breathing rate (four independent methods)
    estimate_rate_psd,
    estimate_rate_peaks,
    estimate_rate_autocorr,
    estimate_rate_zerocross,
    # Nasal / bilateral analysis
    nasal_asymmetry_index,
    bilateral_coherence,
    # Breath intervals & variability
    breath_intervals,
    breathing_variability,
    instantaneous_rate,
    # Signal complexity
    sample_entropy,
    # Artefact detection
    detect_artifacts,
    # Clinical classification
    classify_breathing_pattern,
    # Full-pipeline convenience function
    analyse_recording,
)

__all__ = [
    "bandpass_filter",
    "normalize_signal",
    "detect_breath_peaks",
    "estimate_rate_psd",
    "estimate_rate_peaks",
    "estimate_rate_autocorr",
    "estimate_rate_zerocross",
    "nasal_asymmetry_index",
    "bilateral_coherence",
    "breath_intervals",
    "breathing_variability",
    "instantaneous_rate",
    "sample_entropy",
    "detect_artifacts",
    "classify_breathing_pattern",
    "analyse_recording",
]
