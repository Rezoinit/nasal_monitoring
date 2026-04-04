# analysis/find_threshold.py
# ─────────────────────────────────────────────────
# Adaptive Threshold Finder
#
# PURPOSE:
#   Run this BEFORE a study session to find the
#   optimal threshold for each individual participant
#   and each scenario you care about.
#
# HOW IT WORKS:
#   1. Guides participant through calibration scenarios
#   2. Records raw mic data for each scenario
#   3. Calculates statistics per scenario
#   4. Recommends thresholds
#   5. Saves results to JSON config file
#
# OUTPUT:
#   thresholds_TIMESTAMP.json — load this in analysis
#
# IMPORTANT:
#   This file is analysis-only.
#   It never modifies or affects raw data recording.
#   Raw data is always saved at full fidelity
#   regardless of thresholds found here.
# ─────────────────────────────────────────────────

import json
import time
import serial
import serial.tools.list_ports
import statistics
from dataclasses import dataclass, asdict
from typing      import List, Dict, Optional


# ── CALIBRATION SCENARIOS ─────────────────────────
# Add or remove scenarios to match your study design.
# Each scenario will be recorded for DURATION_SEC seconds.

SCENARIOS = [
    {
        "id":          "baseline",
        "label":       "Baseline — Sit still, breathe normally",
        "description": "Normal resting breathing through nose. "
                       "Used to establish noise floor.",
        "duration_sec": 30,
    },
    {
        "id":          "left_nostril",
        "label":       "Left nostril only — Close right with finger",
        "description": "Breathe only through left nostril. "
                       "Establishes left mic signal level.",
        "duration_sec": 20,
    },
    {
        "id":          "right_nostril",
        "label":       "Right nostril only — Close left with finger",
        "description": "Breathe only through right nostril. "
                       "Establishes right mic signal level.",
        "duration_sec": 20,
    },
    {
        "id":          "deep_breath",
        "label":       "Deep breathing — Slow deep nasal breaths",
        "description": "Slow and deep breaths through nose. "
                       "Establishes upper signal range.",
        "duration_sec": 20,
    },
    {
        "id":          "shallow_breath",
        "label":       "Shallow breathing — Very gentle nasal breaths",
        "description": "Breathe as quietly as possible through nose. "
                       "Establishes lower breath signal.",
        "duration_sec": 20,
    },
    {
        "id":          "mouth_breath",
        "label":       "Mouth breathing — Breathe through mouth only",
        "description": "Breathe only through mouth, nose closed. "
                       "Establishes true noise floor (no nasal signal).",
        "duration_sec": 20,
    },
    {
        "id":          "talking",
        "label":       "Talking — Count out loud from 1 to 30",
        "description": "Tests mic response to speech/movement artefacts.",
        "duration_sec": 20,
    },
    {
        "id":          "head_movement",
        "label":       "Head movement — Slowly nod and turn head",
        "description": "Tests mic response to motion artefacts. "
                       "Slow nods + left/right turns.",
        "duration_sec": 20,
    },
]


# ── THRESHOLD METHODS ─────────────────────────────
# Different ways to calculate a threshold from data.
# All are calculated and saved — you choose in analysis.

def calc_thresholds(values: List[float]) -> Dict[str, float]:
    """
    Calculate multiple threshold candidates from a list of values.
    All methods saved — pick the best one during analysis.
    """
    if not values:
        return {}

    mean   = statistics.mean(values)
    stdev  = statistics.stdev(values) if len(values) > 1 else 0
    sorted_vals = sorted(values)
    n      = len(sorted_vals)

    def percentile(p):
        idx = int((p / 100.0) * n)
        return sorted_vals[min(idx, n - 1)]

    return {
        # Statistical methods
        "mean":              round(mean, 2),
        "std":               round(stdev, 2),
        "mean_plus_1std":    round(mean + 1 * stdev, 2),
        "mean_plus_2std":    round(mean + 2 * stdev, 2),
        "mean_plus_3std":    round(mean + 3 * stdev, 2),

        # Percentile methods
        "p50":               round(percentile(50), 2),
        "p75":               round(percentile(75), 2),
        "p90":               round(percentile(90), 2),
        "p95":               round(percentile(95), 2),
        "p99":               round(percentile(99), 2),

        # Range info
        "min":               round(min(values), 2),
        "max":               round(max(values), 2),
        "range":             round(max(values) - min(values), 2),

        # Sample count
        "n_samples":         n,
    }


# ── SERIAL CONNECTION ─────────────────────────────

def find_xiao_port() -> str:
    ports = serial.tools.list_ports.comports()
    for p in ports:
        if "usbmodem" in p.device.lower():
            return p.device
    for p in ports:
        if "USB" in p.description:
            return p.device
    raise RuntimeError(
        "XIAO not found. Plug in your board and try again."
    )


def collect_scenario(
    ser:          serial.Serial,
    duration_sec: int,
    scenario_id:  str,
) -> Dict:
    """
    Collect raw mic data for one scenario.
    Returns dict with mic1 and mic2 raw value lists.
    """
    mic1_values = []
    mic2_values = []
    start_time  = time.time()

    print(f"\n  ▶ Recording {scenario_id} "
          f"for {duration_sec} seconds...")

    remaining = duration_sec
    last_print = time.time()

    while time.time() - start_time < duration_sec:

        # Countdown display
        now = time.time()
        remaining = duration_sec - (now - start_time)
        if now - last_print >= 5:
            print(f"    {remaining:.0f}s remaining...")
            last_print = now

        try:
            raw_line = ser.readline().decode("utf-8").strip()
            if not raw_line:
                continue

            data = json.loads(raw_line)

            # Skip startup messages
            if "status" in data:
                continue

            # Collect raw values only
            if "m1" in data and "m2" in data:
                mic1_values.append(data["m1"])
                mic2_values.append(data["m2"])

        except (json.JSONDecodeError, KeyError):
            continue
        except Exception as e:
            print(f"    Warning: {e}")
            continue

    print(f"  ✅ Collected {len(mic1_values)} samples")
    return {
        "mic1": mic1_values,
        "mic2": mic2_values,
    }


# ── RECOMMENDATION ENGINE ─────────────────────────

def recommend_thresholds(results: Dict) -> Dict:
    """
    Compare baseline (noise) vs breathing scenarios
    to recommend a threshold for each mic.

    Logic:
        Good threshold sits between:
        - Above: baseline max (noise floor)
        - Below: shallow breath mean (detect even quiet breaths)
    """
    recommendations = {}

    baseline = results.get("baseline", {})

    for mic in ["mic1", "mic2"]:
        key = f"stats_{mic}"
        base_stats = baseline.get(key, {})

        if not base_stats:
            recommendations[mic] = {
                "note": "No baseline recorded — cannot recommend"
            }
            continue

        noise_floor    = base_stats.get("mean_plus_2std", 80)
        noise_max      = base_stats.get("p99", 80)

        # Find lowest breathing signal across all breath scenarios
        breath_signals = []
        for scenario_id in ["shallow_breath", "baseline",
                             "left_nostril", "right_nostril"]:
            s = results.get(scenario_id, {})
            val = s.get(key, {}).get("p75")
            if val:
                breath_signals.append(val)

        recommendations[mic] = {
            "conservative":  round(noise_max, 1),
            "recommended":   round(noise_floor, 1),
            "aggressive":    round(
                base_stats.get("mean_plus_1std", 60), 1
            ),
            "note": (
                "conservative = catches only clear breaths, "
                "few false positives. "
                "recommended = good balance. "
                "aggressive = catches subtle breaths, "
                "more false positives."
            )
        }

    return recommendations


# ── MAIN ─────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Nasal Monitor — Threshold Calibration Tool")
    print("=" * 60)
    print()
    print("PURPOSE:")
    print("  Find optimal signal thresholds for THIS participant.")
    print("  Results saved to JSON — use during analysis only.")
    print("  Raw data recording is never affected by this tool.")
    print()

    # Participant info
    participant_id = input("Participant ID (e.g. P01): ").strip()
    if not participant_id:
        participant_id = f"P_{int(time.time())}"

    session_notes = input("Session notes (optional): ").strip()

    print()
    print("Connecting to XIAO board...")

    try:
        port = find_xiao_port()
    except RuntimeError as e:
        print(f"ERROR: {e}")
        return

    ser = serial.Serial(port, 115200, timeout=2)
    print(f"Connected to {port}")

    # Wait for board ready message
    print("Waiting for board...")
    time.sleep(3)
    ser.reset_input_buffer()

    # ── Run each scenario ─────────────────────────
    all_results = {}

    print()
    print("=" * 60)
    print(f"  CALIBRATION — {len(SCENARIOS)} scenarios")
    print("=" * 60)

    for i, scenario in enumerate(SCENARIOS, 1):
        print()
        print(f"SCENARIO {i}/{len(SCENARIOS)}: {scenario['label']}")
        print(f"  {scenario['description']}")
        print()

        # Countdown before recording
        for countdown in range(5, 0, -1):
            print(f"  Starting in {countdown}...", end="\r")
            time.sleep(1)
        print("  GO!                    ")

        # Collect data
        raw_data = collect_scenario(
            ser,
            scenario["duration_sec"],
            scenario["id"],
        )

        # Calculate statistics for both mics
        all_results[scenario["id"]] = {
            "label":      scenario["label"],
            "duration_sec": scenario["duration_sec"],
            "n_samples":  len(raw_data["mic1"]),
            "stats_mic1": calc_thresholds(raw_data["mic1"]),
            "stats_mic2": calc_thresholds(raw_data["mic2"]),
        }

        # Show quick summary after each scenario
        s1 = all_results[scenario["id"]]["stats_mic1"]
        s2 = all_results[scenario["id"]]["stats_mic2"]
        print(f"\n  Summary for {scenario['id']}:")
        print(f"    MIC1: mean={s1.get('mean','?'):6}  "
              f"std={s1.get('std','?'):5}  "
              f"p90={s1.get('p90','?'):6}  "
              f"max={s1.get('max','?'):6}")
        print(f"    MIC2: mean={s2.get('mean','?'):6}  "
              f"std={s2.get('std','?'):5}  "
              f"p90={s2.get('p90','?'):6}  "
              f"max={s2.get('max','?'):6}")

        # Rest between scenarios
        if i < len(SCENARIOS):
            print()
            print("  Resting 5 seconds before next scenario...")
            time.sleep(5)

    ser.close()

    # ── Generate recommendations ──────────────────
    recommendations = recommend_thresholds(all_results)

    # ── Build output ──────────────────────────────
    output = {
        "metadata": {
            "participant_id":   participant_id,
            "session_notes":    session_notes,
            "recorded_at":      time.strftime("%Y-%m-%d %H:%M:%S"),
            "unix_timestamp":   time.time(),
            "board_port":       port,
            "n_scenarios":      len(SCENARIOS),
            "tool_version":     "1.0.0",
            "important_note": (
                "These thresholds are for POST-HOC ANALYSIS ONLY. "
                "Raw data recording never uses thresholds. "
                "Apply these during analysis of saved CSV files."
            ),
        },
        "recommendations": recommendations,
        "scenarios":        all_results,
    }

    # ── Save to file ──────────────────────────────
    filename = (
        f"thresholds_{participant_id}_"
        f"{int(time.time())}.json"
    )

    with open(filename, "w") as f:
        json.dump(output, f, indent=2)

    # ── Print summary ─────────────────────────────
    print()
    print("=" * 60)
    print("  CALIBRATION COMPLETE")
    print("=" * 60)
    print()
    print(f"Participant : {participant_id}")
    print(f"Saved to   : {filename}")
    print()
    print("THRESHOLD RECOMMENDATIONS:")
    print()

    for mic, rec in recommendations.items():
        print(f"  {mic.upper()}:")
        if "note" in rec and "cannot" in rec["note"]:
            print(f"    {rec['note']}")
        else:
            print(f"    Conservative : {rec.get('conservative','?')}")
            print(f"    Recommended  : {rec.get('recommended','?')}")
            print(f"    Aggressive   : {rec.get('aggressive','?')}")
        print()

    print("HOW TO USE IN ANALYSIS:")
    print(f"  import json")
    print(f"  with open('{filename}') as f:")
    print(f"      config = json.load(f)")
    print(f"  threshold_mic1 = config['recommendations']"
          f"['mic1']['recommended']")
    print(f"  threshold_mic2 = config['recommendations']"
          f"['mic2']['recommended']")
    print()
    print("Remember: Apply these thresholds to your saved CSV")
    print("files during analysis — never to live recording.")


if __name__ == "__main__":
    main()