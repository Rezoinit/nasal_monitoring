"""
Nasal Monitor — Threshold Calibration Server
═══════════════════════════════════════════════════════════

Run this file, then open http://localhost:5500 in Chrome.

    python analysis/threshold_server.py

What it does:
  1. Serves a guided calibration UI in Chrome
  2. Reads raw mic data from XIAO over USB Serial
  3. Guides participant through breathing scenarios
  4. Saves raw data to CSV (full fidelity, no filtering)
  5. Saves threshold recommendations to JSON (for analysis only)

Outputs:
  calibration/raw_PARTICIPANTID_TIMESTAMP.csv
  calibration/thresholds_PARTICIPANTID_TIMESTAMP.json

IMPORTANT:
  Thresholds are for post-hoc analysis ONLY.
  Raw data is always saved at full fidelity.
"""

import json
import time
import threading
import statistics
import csv
import os
import webbrowser
import serial
import serial.tools.list_ports
from datetime  import datetime
from flask     import Flask, render_template_string
from flask_socketio import SocketIO, emit

# ── CONFIG ────────────────────────────────────────────────
PORT        = 5500
BAUD_RATE   = 115200
OUTPUT_DIR  = "calibration"

# ── SCENARIOS ─────────────────────────────────────────────
SCENARIOS = [
    {
        "id":           "baseline",
        "title":        "Baseline",
        "instruction":  "Breathe normally through your nose.\nSit still and relax.",
        "cue":          "normal",
        "duration":     30,
        "color":        "#64b5f6",
        "icon":         "◎",
    },
    {
        "id":           "mouth_breathing",
        "title":        "Mouth Only",
        "instruction":  "Breathe through your mouth only.\nKeep your nose completely closed.",
        "cue":          "mouth",
        "duration":     20,
        "color":        "#ef9a9a",
        "icon":         "○",
    },
    {
        "id":           "left_nostril",
        "title":        "Left Nostril",
        "instruction":  "Close your right nostril with your finger.\nBreathe only through your left nostril.",
        "cue":          "left",
        "duration":     20,
        "color":        "#a5d6a7",
        "icon":         "◑",
    },
    {
        "id":           "right_nostril",
        "title":        "Right Nostril",
        "instruction":  "Close your left nostril with your finger.\nBreathe only through your right nostril.",
        "cue":          "right",
        "duration":     20,
        "color":        "#ce93d8",
        "icon":         "◐",
    },
    {
        "id":           "deep_breath",
        "title":        "Deep Breathing",
        "instruction":  "Take slow, deep breaths through your nose.\nInhale fully, exhale slowly.",
        "cue":          "deep",
        "duration":     20,
        "color":        "#ffcc80",
        "icon":         "◉",
    },
    {
        "id":           "shallow_breath",
        "title":        "Shallow Breathing",
        "instruction":  "Breathe as gently as possible through your nose.\nVery quiet, minimal effort.",
        "cue":          "shallow",
        "duration":     20,
        "color":        "#80deea",
        "icon":         "◌",
    },
    {
        "id":           "talking",
        "title":        "Talking",
        "instruction":  "Count out loud slowly from 1 to 30.\nKeep your mics in place.",
        "cue":          "talk",
        "duration":     20,
        "color":        "#f48fb1",
        "icon":         "◎",
    },
    {
        "id":           "head_movement",
        "title":        "Head Movement",
        "instruction":  "Slowly nod your head up and down.\nThen slowly turn left and right.\nRepeat gently.",
        "cue":          "move",
        "duration":     20,
        "color":        "#bcaaa4",
        "icon":         "↕",
    },
]

# ── HTML UI ───────────────────────────────────────────────
HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Nasal Monitor — Calibration</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.min.js"></script>
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@300;400;500&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:        #0a0e14;
    --surface:   #111720;
    --border:    #1e2a38;
    --text:      #e2e8f0;
    --muted:     #64748b;
    --accent:    #64b5f6;
    --success:   #a5d6a7;
    --warning:   #ffcc80;
    --radius:    16px;
  }

  html, body {
    height: 100%;
    background: var(--bg);
    color: var(--text);
    font-family: 'DM Sans', sans-serif;
    overflow: hidden;
  }

  /* ── SCREENS ── */
  .screen {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 40px;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.5s ease;
  }
  .screen.active {
    opacity: 1;
    pointer-events: all;
  }

  /* ── WELCOME SCREEN ── */
  .logo {
    font-family: 'DM Mono', monospace;
    font-size: 11px;
    letter-spacing: 4px;
    color: var(--muted);
    text-transform: uppercase;
    margin-bottom: 48px;
  }
  .welcome-title {
    font-size: 42px;
    font-weight: 300;
    letter-spacing: -1px;
    margin-bottom: 12px;
    text-align: center;
  }
  .welcome-sub {
    color: var(--muted);
    font-size: 16px;
    margin-bottom: 64px;
    text-align: center;
    line-height: 1.6;
  }
  .input-group {
    display: flex;
    flex-direction: column;
    gap: 12px;
    width: 380px;
    margin-bottom: 32px;
  }
  .input-label {
    font-family: 'DM Mono', monospace;
    font-size: 11px;
    letter-spacing: 3px;
    color: var(--muted);
    text-transform: uppercase;
  }
  input[type="text"] {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px 20px;
    font-size: 18px;
    color: var(--text);
    font-family: 'DM Sans', sans-serif;
    outline: none;
    transition: border-color 0.2s;
    width: 100%;
  }
  input[type="text"]:focus {
    border-color: var(--accent);
  }
  .btn {
    background: var(--accent);
    color: #0a0e14;
    border: none;
    border-radius: 12px;
    padding: 16px 40px;
    font-size: 16px;
    font-weight: 600;
    font-family: 'DM Sans', sans-serif;
    cursor: pointer;
    transition: opacity 0.2s, transform 0.1s;
    letter-spacing: 0.3px;
  }
  .btn:hover { opacity: 0.9; transform: translateY(-1px); }
  .btn:active { transform: translateY(0); }
  .btn:disabled { opacity: 0.4; cursor: not-allowed; transform: none; }
  .btn-ghost {
    background: transparent;
    color: var(--muted);
    border: 1px solid var(--border);
  }
  .btn-ghost:hover { border-color: var(--text); color: var(--text); }

  /* ── STATUS PILL ── */
  .status-pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 100px;
    padding: 8px 18px;
    font-family: 'DM Mono', monospace;
    font-size: 12px;
    color: var(--muted);
    margin-bottom: 48px;
  }
  .status-dot {
    width: 7px; height: 7px;
    border-radius: 50%;
    background: var(--muted);
  }
  .status-dot.connected { background: var(--success); box-shadow: 0 0 6px var(--success); }
  .status-dot.error     { background: #ef9a9a; }

  /* ── OVERVIEW SCREEN ── */
  .overview-title {
    font-size: 32px;
    font-weight: 300;
    margin-bottom: 8px;
    text-align: center;
  }
  .overview-sub {
    color: var(--muted);
    font-size: 14px;
    margin-bottom: 48px;
    text-align: center;
  }
  .scenario-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
    width: 100%;
    max-width: 880px;
    margin-bottom: 48px;
  }
  .scenario-chip {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px;
    text-align: center;
  }
  .scenario-chip .chip-icon {
    font-size: 22px;
    margin-bottom: 8px;
    display: block;
  }
  .scenario-chip .chip-title {
    font-size: 13px;
    font-weight: 500;
    margin-bottom: 4px;
  }
  .scenario-chip .chip-dur {
    font-family: 'DM Mono', monospace;
    font-size: 11px;
    color: var(--muted);
  }

  /* ── CALIBRATION SCREEN ── */
  .cal-header {
    display: flex;
    align-items: center;
    gap: 20px;
    margin-bottom: 60px;
    width: 100%;
    max-width: 700px;
  }
  .cal-progress-track {
    flex: 1;
    height: 3px;
    background: var(--border);
    border-radius: 10px;
    overflow: hidden;
  }
  .cal-progress-fill {
    height: 100%;
    background: var(--accent);
    border-radius: 10px;
    transition: width 0.5s ease;
  }
  .cal-step {
    font-family: 'DM Mono', monospace;
    font-size: 12px;
    color: var(--muted);
    white-space: nowrap;
  }

  /* ── CIRCLE GUIDE ── */
  .circle-wrap {
    position: relative;
    width: 280px;
    height: 280px;
    margin-bottom: 48px;
  }
  .circle-svg {
    width: 280px;
    height: 280px;
    transform: rotate(-90deg);
  }
  .circle-bg {
    fill: none;
    stroke: var(--border);
    stroke-width: 4;
  }
  .circle-progress {
    fill: none;
    stroke-width: 4;
    stroke-linecap: round;
    transition: stroke-dashoffset 1s linear, stroke 0.5s;
  }
  .circle-inner {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    padding: 40px;
  }
  .circle-countdown {
    font-size: 64px;
    font-weight: 300;
    line-height: 1;
    margin-bottom: 4px;
    font-family: 'DM Mono', monospace;
    transition: color 0.5s;
  }
  .circle-label {
    font-size: 12px;
    color: var(--muted);
    letter-spacing: 2px;
    text-transform: uppercase;
    font-family: 'DM Mono', monospace;
  }

  /* ── BREATHING RING (animated) ── */
  .breath-ring {
    position: absolute;
    inset: 20px;
    border-radius: 50%;
    border: 2px solid transparent;
    opacity: 0;
    transition: opacity 0.5s;
  }
  .breath-ring.active {
    opacity: 1;
    animation: breathe 4s ease-in-out infinite;
  }
  @keyframes breathe {
    0%, 100% { transform: scale(0.92); opacity: 0.3; }
    50%       { transform: scale(1.08); opacity: 0.8; }
  }

  /* ── SCENARIO INFO ── */
  .scenario-title {
    font-size: 28px;
    font-weight: 400;
    margin-bottom: 16px;
    text-align: center;
  }
  .scenario-instruction {
    font-size: 16px;
    color: var(--muted);
    line-height: 1.8;
    text-align: center;
    max-width: 480px;
    white-space: pre-line;
  }

  /* ── LIVE MIC BARS ── */
  .mic-bars {
    display: flex;
    gap: 16px;
    margin-top: 40px;
  }
  .mic-bar-wrap {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
  }
  .mic-bar-track {
    width: 6px;
    height: 80px;
    background: var(--border);
    border-radius: 10px;
    position: relative;
    overflow: hidden;
  }
  .mic-bar-fill {
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    background: var(--accent);
    border-radius: 10px;
    transition: height 0.1s;
  }
  .mic-bar-label {
    font-family: 'DM Mono', monospace;
    font-size: 10px;
    color: var(--muted);
    letter-spacing: 1px;
  }

  /* ── GET READY SCREEN ── */
  .ready-icon {
    font-size: 64px;
    margin-bottom: 32px;
    display: block;
    transition: transform 0.3s ease;
  }
  .ready-title {
    font-size: 13px;
    font-family: 'DM Mono', monospace;
    letter-spacing: 4px;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 16px;
  }
  .ready-scenario {
    font-size: 38px;
    font-weight: 300;
    margin-bottom: 20px;
    text-align: center;
  }
  .ready-instruction {
    font-size: 16px;
    color: var(--muted);
    line-height: 1.8;
    text-align: center;
    max-width: 460px;
    white-space: pre-line;
    margin-bottom: 56px;
  }
  .btn-ready {
    font-size: 18px;
    padding: 20px 60px;
    border-radius: 100px;
    letter-spacing: 0.5px;
    animation: pulse-btn 2s ease-in-out infinite;
  }
  @keyframes pulse-btn {
    0%, 100% { box-shadow: 0 0 0 0 rgba(100,181,246,0.4); }
    50%       { box-shadow: 0 0 0 16px rgba(100,181,246,0); }
  }
  .ready-step {
    margin-top: 24px;
    font-family: 'DM Mono', monospace;
    font-size: 11px;
    color: var(--muted);
    letter-spacing: 2px;
  }

  /* ── REST SCREEN ── */
  .rest-title {
    font-size: 36px;
    font-weight: 300;
    margin-bottom: 16px;
    text-align: center;
  }
  .rest-sub {
    color: var(--muted);
    font-size: 16px;
    margin-bottom: 48px;
    text-align: center;
  }
  .rest-counter {
    font-family: 'DM Mono', monospace;
    font-size: 72px;
    font-weight: 300;
    color: var(--accent);
  }

  /* ── DONE SCREEN ── */
  .done-title {
    font-size: 42px;
    font-weight: 300;
    margin-bottom: 12px;
    text-align: center;
  }
  .done-sub {
    color: var(--muted);
    font-size: 16px;
    margin-bottom: 56px;
    text-align: center;
  }
  .results-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    width: 100%;
    max-width: 600px;
    margin-bottom: 48px;
  }
  .result-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 24px;
  }
  .result-mic {
    font-family: 'DM Mono', monospace;
    font-size: 11px;
    letter-spacing: 3px;
    color: var(--muted);
    text-transform: uppercase;
    margin-bottom: 16px;
  }
  .result-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 0;
    border-bottom: 1px solid var(--border);
  }
  .result-row:last-child { border-bottom: none; }
  .result-key {
    font-size: 13px;
    color: var(--muted);
  }
  .result-val {
    font-family: 'DM Mono', monospace;
    font-size: 14px;
    font-weight: 500;
  }
  .result-val.recommended { color: var(--success); }
  .result-val.conservative { color: var(--warning); }

  .save-info {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px 28px;
    font-family: 'DM Mono', monospace;
    font-size: 12px;
    color: var(--muted);
    text-align: center;
    line-height: 2;
    max-width: 600px;
    width: 100%;
    margin-bottom: 32px;
  }
  .save-info span { color: var(--text); }

  /* ── TOAST ── */
  .toast {
    position: fixed;
    bottom: 32px;
    left: 50%;
    transform: translateX(-50%) translateY(80px);
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 100px;
    padding: 12px 24px;
    font-size: 13px;
    color: var(--muted);
    transition: transform 0.3s ease;
    z-index: 100;
    white-space: nowrap;
  }
  .toast.show { transform: translateX(-50%) translateY(0); }

  /* ── GRID BG ── */
  body::before {
    content: '';
    position: fixed;
    inset: 0;
    background-image:
      linear-gradient(rgba(100,181,246,0.02) 1px, transparent 1px),
      linear-gradient(90deg, rgba(100,181,246,0.02) 1px, transparent 1px);
    background-size: 48px 48px;
    pointer-events: none;
  }
</style>
</head>
<body>

<!-- ══ SCREEN 1: WELCOME ══════════════════════════════ -->
<div class="screen active" id="screen-welcome">
  <div class="logo">Nasal Monitor Research Tool</div>
  <h1 class="welcome-title">Breathing Calibration</h1>
  <p class="welcome-sub">
    Guides the participant through breathing scenarios<br>
    to establish personalized signal thresholds.
  </p>

  <div id="conn-status" class="status-pill">
    <div class="status-dot" id="dot"></div>
    <span id="conn-text">Connecting to board...</span>
  </div>

  <div class="input-group">
    <div class="input-label">Participant ID</div>
    <input type="text" id="pid-input" placeholder="e.g. P01" autocomplete="off" />
  </div>
  <div class="input-group">
    <div class="input-label">Session Notes (optional)</div>
    <input type="text" id="notes-input" placeholder="e.g. pre-task, eyes open" autocomplete="off" />
  </div>

  <button class="btn" id="btn-start" onclick="goOverview()" disabled>
    Begin Calibration
  </button>
</div>

<!-- ══ SCREEN 2: OVERVIEW ══════════════════════════════ -->
<div class="screen" id="screen-overview">
  <h2 class="overview-title">Calibration Overview</h2>
  <p class="overview-sub">8 scenarios · ~3 minutes total · participant sits still with mics in place</p>

  <div class="scenario-grid" id="scenario-grid"></div>

  <button class="btn" onclick="startCalibration()">Start Now</button>
</div>

<!-- ══ SCREEN 2.5: GET READY ═══════════════════════════ -->
<div class="screen" id="screen-ready">
  <div class="ready-title">Next Scenario</div>
  <span class="ready-icon" id="ready-icon">◎</span>
  <h2 class="ready-scenario" id="ready-scenario-title">–</h2>
  <p class="ready-instruction" id="ready-instruction">–</p>
  <button class="btn btn-ready" id="btn-ready" onclick="participantReady()">
    I'm Ready — Start
  </button>
  <div class="ready-step" id="ready-step">–</div>
  <div style="margin-top:14px;font-family:'DM Mono',monospace;font-size:11px;
              color:var(--muted);letter-spacing:1px;">
    press <kbd style="background:var(--border);border-radius:4px;
                      padding:2px 7px;font-size:11px;">space</kbd>
    or click to start
  </div>
</div>

<!-- ══ SCREEN 3: CALIBRATION ══════════════════════════ -->
<div class="screen" id="screen-cal">
  <div class="cal-header">
    <div class="cal-step" id="cal-step-label">1 / 8</div>
    <div class="cal-progress-track">
      <div class="cal-progress-fill" id="cal-progress" style="width:0%"></div>
    </div>
    <div class="cal-step" id="cal-time-label">–</div>
  </div>

  <div class="circle-wrap">
    <svg class="circle-svg" viewBox="0 0 280 280">
      <circle class="circle-bg" cx="140" cy="140" r="128"/>
      <circle class="circle-progress" id="circle-prog"
              cx="140" cy="140" r="128"
              stroke-dasharray="804.25"
              stroke-dashoffset="804.25"/>
    </svg>
    <div class="breath-ring" id="breath-ring"></div>
    <div class="circle-inner">
      <div class="circle-countdown" id="circle-num">–</div>
      <div class="circle-label">seconds</div>
    </div>
  </div>

  <h2 class="scenario-title" id="cal-title">–</h2>
  <p class="scenario-instruction" id="cal-instruction">–</p>

  <div class="mic-bars">
    <div class="mic-bar-wrap">
      <div class="mic-bar-track">
        <div class="mic-bar-fill" id="bar1" style="height:0%"></div>
      </div>
      <div class="mic-bar-label">M1</div>
    </div>
    <div class="mic-bar-wrap">
      <div class="mic-bar-track">
        <div class="mic-bar-fill" id="bar2" style="height:0%"></div>
      </div>
      <div class="mic-bar-label">M2</div>
    </div>
  </div>
</div>

<!-- ══ SCREEN 4: REST ══════════════════════════════════ -->
<div class="screen" id="screen-rest">
  <h2 class="rest-title">Well done.</h2>
  <p class="rest-sub">Take a short break before the next scenario.</p>
  <div class="rest-counter" id="rest-num">5</div>
</div>

<!-- ══ SCREEN 5: DONE ══════════════════════════════════ -->
<div class="screen" id="screen-done">
  <h2 class="done-title">Calibration Complete</h2>
  <p class="done-sub">All scenarios recorded. Results saved.</p>

  <div class="results-grid" id="results-grid"></div>

  <div class="save-info" id="save-info">Saving...</div>

  <button class="btn" onclick="location.reload()">
    New Participant
  </button>
</div>

<!-- ── TOAST ── -->
<div class="toast" id="toast"></div>

<script>
const socket = io();

// ── STATE ──────────────────────────────────────────────
let participantId   = '';
let sessionNotes    = '';
let currentScenario = 0;
let scenarios       = [];
let isConnected     = false;
let latestMic1      = 0;
let latestMic2      = 0;
let countdownTimer  = null;
let currentSec      = 0;
const CIRCUMFERENCE = 804.25;  // 2π × 128

// ── SOCKET EVENTS ──────────────────────────────────────
socket.on('connect', () => {
  socket.emit('get_scenarios');
  socket.emit('check_board');
});

socket.on('scenarios', data => {
  scenarios = data;
  buildOverviewGrid();
});

socket.on('board_status', data => {
  isConnected = data.connected;
  const dot  = document.getElementById('dot');
  const text = document.getElementById('conn-text');
  const btn  = document.getElementById('btn-start');
  if (data.connected) {
    dot.className  = 'status-dot connected';
    text.textContent = `Board connected · ${data.port}`;
    btn.disabled   = false;
  } else {
    dot.className  = 'status-dot error';
    text.textContent = data.message || 'Board not found';
    btn.disabled   = true;
  }
});

socket.on('raw_reading', data => {
  latestMic1 = data.m1;
  latestMic2 = data.m2;
  updateMicBars(data.m1, data.m2);
});

socket.on('calibration_done', data => {
  showDoneScreen(data);
});

socket.on('toast', msg => showToast(msg));

// ── SCREEN MANAGEMENT ──────────────────────────────────
function showScreen(id) {
  document.querySelectorAll('.screen').forEach(s => {
    s.classList.remove('active');
  });
  document.getElementById(id).classList.add('active');
}

// ── OVERVIEW GRID ──────────────────────────────────────
function buildOverviewGrid() {
  const grid = document.getElementById('scenario-grid');
  grid.innerHTML = scenarios.map((s, i) => `
    <div class="scenario-chip">
      <span class="chip-icon" style="color:${s.color}">${s.icon}</span>
      <div class="chip-title">${s.title}</div>
      <div class="chip-dur">${s.duration}s</div>
    </div>
  `).join('');
}

// ── WELCOME → OVERVIEW ────────────────────────────────
function goOverview() {
  participantId = document.getElementById('pid-input').value.trim();
  sessionNotes  = document.getElementById('notes-input').value.trim();
  if (!participantId) {
    document.getElementById('pid-input').focus();
    showToast('Please enter a participant ID');
    return;
  }
  showScreen('screen-overview');
}

// ── START CALIBRATION ──────────────────────────────────
function startCalibration() {
  socket.emit('start_calibration', {
    participant_id: participantId,
    notes:          sessionNotes,
  });
  currentScenario = 0;
  showScenario(0);   // shows Get Ready screen for scenario 1
}

// ── SHOW GET READY SCREEN ────────────────────────────
// Called between rest and recording.
// Participant presses button when ready.
function showScenario(idx) {
  if (idx >= scenarios.length) return;

  const s = scenarios[idx];
  currentScenario = idx;

  // Populate the Get Ready screen
  document.getElementById('ready-icon').textContent         = s.icon;
  document.getElementById('ready-icon').style.color         = s.color;
  document.getElementById('ready-scenario-title').textContent = s.title;
  document.getElementById('ready-instruction').textContent  = s.instruction;
  document.getElementById('ready-step').textContent =
    `Scenario ${idx + 1} of ${scenarios.length}  ·  ${s.duration}s`;

  // Style the ready button to match scenario color
  const btn = document.getElementById('btn-ready');
  btn.style.background = s.color;
  btn.style.animation  = 'pulse-btn 2s ease-in-out infinite';

  showScreen('screen-ready');
}

// ── PARTICIPANT PRESSES READY ─────────────────────────
function participantReady() {
  const s   = scenarios[currentScenario];
  const btn = document.getElementById('btn-ready');

  // Disable button so it can't be pressed twice
  btn.disabled = true;
  btn.textContent = 'Recording…';
  btn.style.animation = 'none';

  // Prep calibration screen
  document.getElementById('cal-step-label').textContent =
    `${currentScenario + 1} / ${scenarios.length}`;
  document.getElementById('cal-title').textContent       = s.title;
  document.getElementById('cal-instruction').textContent = s.instruction;
  document.getElementById('circle-prog').style.stroke    = s.color;
  document.getElementById('circle-num').style.color      = s.color;
  document.getElementById('bar1').style.background       = s.color;
  document.getElementById('bar2').style.background       = s.color;

  const ring = document.getElementById('breath-ring');
  ring.style.borderColor = s.color;
  ring.classList.add('active');

  showScreen('screen-cal');
  startCountdown(s.duration, s.id, currentScenario);

  // Re-enable for next time
  setTimeout(() => {
    btn.disabled    = false;
    btn.textContent = 'I\'m Ready — Start';
  }, 1000);
}

// ── COUNTDOWN ──────────────────────────────────────────
function startCountdown(totalSec, scenarioId, idx) {
  let remaining = totalSec;
  currentSec    = totalSec;

  socket.emit('record_scenario', { scenario_id: scenarioId });

  updateCircle(remaining, totalSec);

  clearInterval(countdownTimer);
  countdownTimer = setInterval(() => {
    remaining--;
    updateCircle(remaining, totalSec);

    if (remaining <= 0) {
      clearInterval(countdownTimer);
      socket.emit('stop_scenario', { scenario_id: scenarioId });
      document.getElementById('breath-ring').classList.remove('active');

      const nextIdx = idx + 1;
      if (nextIdx < scenarios.length) {
        showRest(nextIdx);
      } else {
        socket.emit('finish_calibration');
        showScreen('screen-rest');
        document.getElementById('rest-num').textContent = '…';
        document.querySelector('#screen-rest .rest-sub').textContent =
          'Calculating thresholds…';
      }
    }
  }, 1000);
}

function updateCircle(remaining, total) {
  const pct    = remaining / total;
  const offset = CIRCUMFERENCE * (1 - pct);
  document.getElementById('circle-prog').style.strokeDashoffset = offset;
  document.getElementById('circle-num').textContent = remaining;
  document.getElementById('cal-progress').style.width =
    `${(currentScenario / scenarios.length) * 100}%`;
  document.getElementById('cal-time-label').textContent =
    formatTime(remaining);
}

function formatTime(sec) {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

// ── REST BETWEEN SCENARIOS ────────────────────────────
// Short auto-countdown rest, then → Get Ready screen
function showRest(nextIdx) {
  showScreen('screen-rest');
  document.querySelector('#screen-rest .rest-sub').textContent =
    'Take a short break before the next scenario.';
  let restSec = 5;
  document.getElementById('rest-num').textContent = restSec;


  const restTimer = setInterval(() => {
    restSec--;
    document.getElementById('rest-num').textContent = restSec;
    if (restSec <= 0) {
      clearInterval(restTimer);
      showScenario(nextIdx);
    }
  }, 1000);
}

// ── MIC BARS ──────────────────────────────────────────
function updateMicBars(m1, m2) {
  const MAX = 300;
  document.getElementById('bar1').style.height =
    `${Math.min((m1 / MAX) * 100, 100)}%`;
  document.getElementById('bar2').style.height =
    `${Math.min((m2 / MAX) * 100, 100)}%`;
}

// ── DONE SCREEN ──────────────────────────────────────
function showDoneScreen(data) {
  showScreen('screen-done');

  const grid = document.getElementById('results-grid');
  grid.innerHTML = ['mic1', 'mic2'].map(mic => {
    const r   = data.recommendations[mic] || {};
    const lab = mic === 'mic1' ? 'MIC1 — Yellow' : 'MIC2 — Blue';
    return `
      <div class="result-card">
        <div class="result-mic">${lab}</div>
        <div class="result-row">
          <span class="result-key">Aggressive</span>
          <span class="result-val">${r.aggressive ?? '—'}</span>
        </div>
        <div class="result-row">
          <span class="result-key">Recommended</span>
          <span class="result-val recommended">${r.recommended ?? '—'}</span>
        </div>
        <div class="result-row">
          <span class="result-key">Conservative</span>
          <span class="result-val conservative">${r.conservative ?? '—'}</span>
        </div>
      </div>
    `;
  }).join('');

  const info = document.getElementById('save-info');
  info.innerHTML = `
    Raw data → <span>${data.csv_file}</span><br>
    Thresholds → <span>${data.json_file}</span><br>
    <br>
    <span style="color:var(--muted)">
      Apply thresholds to saved CSV during analysis only.
      Raw data always saved at full fidelity.
    </span>
  `;
}

// ── TOAST ─────────────────────────────────────────────
function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2500);
}

// ── SPACEBAR SHORTCUT ─────────────────────────────────
// Press Space to trigger the Ready button when visible.
// Prevents accidental triggers on other screens.
document.addEventListener('keydown', e => {
  if (e.code !== 'Space') return;
  if (e.target.tagName === 'INPUT') return;  // don't fire while typing

  const readyScreen = document.getElementById('screen-ready');
  const btn         = document.getElementById('btn-ready');

  // Only fire if Get Ready screen is currently active and button enabled
  if (readyScreen.classList.contains('active') && !btn.disabled) {
    e.preventDefault();   // stop page from scrolling
    btn.click();
  }
});
</script>
</body>
</html>
"""

# ── FLASK APP ─────────────────────────────────────────────
app    = Flask(__name__)
app.config['SECRET_KEY'] = 'nasal_monitor_2024'
socketio = SocketIO(app, cors_allowed_origins="*")

# ── GLOBAL STATE ──────────────────────────────────────────
class SessionState:
    def __init__(self):
        self.reset()

    def reset(self):
        self.participant_id   = None
        self.session_notes    = None
        self.serial_conn      = None
        self.running          = False
        self.current_scenario = None
        self.raw_data         = {}      # scenario_id → list of readings
        self.all_raw          = []      # every reading across whole session
        self.csv_writer       = None
        self.csv_file         = None
        self.csv_handle       = None
        self.start_time       = None

state = SessionState()


# ── SERIAL HELPERS ────────────────────────────────────────

def find_xiao():
    ports = serial.tools.list_ports.comports()
    for p in ports:
        if "usbmodem" in p.device.lower():
            return p.device
    for p in ports:
        if "USB" in p.description:
            return p.device
    return None


def serial_read_loop():
    """Background thread — reads serial, emits to browser."""
    while state.running and state.serial_conn:
        try:
            line = state.serial_conn.readline().decode("utf-8").strip()
            if not line:
                continue

            data = json.loads(line)
            if "status" in data:
                continue

            reading = {
                "t":    data["t"],
                "seq":  data["seq"],
                "m1":   data["m1"],
                "m2":   data["m2"],
                "temp": data["temp"] / 4.0,
                "host": time.time(),
            }

            # Save to CSV
            if state.csv_writer:
                state.csv_writer.writerow([
                    f"{reading['host']:.4f}",
                    reading["t"],
                    reading["seq"],
                    reading["m1"],
                    reading["m2"],
                    f"{reading['temp']:.2f}",
                    state.current_scenario or "none",
                ])
                state.csv_handle.flush()

            # Accumulate per scenario
            if state.current_scenario:
                if state.current_scenario not in state.raw_data:
                    state.raw_data[state.current_scenario] = []
                state.raw_data[state.current_scenario].append(reading)

            state.all_raw.append(reading)

            # Emit to browser for live display
            socketio.emit('raw_reading', {'m1': data["m1"], 'm2': data["m2"]})

        except (json.JSONDecodeError, KeyError):
            continue
        except Exception:
            break


# ── THRESHOLD CALCULATIONS ────────────────────────────────

def calc_stats(values):
    if not values or len(values) < 2:
        return {}
    mean  = statistics.mean(values)
    stdev = statistics.stdev(values)
    sv    = sorted(values)
    n     = len(sv)

    def pct(p):
        return sv[min(int(p / 100 * n), n - 1)]

    return {
        "mean":           round(mean,  2),
        "std":            round(stdev, 2),
        "mean_plus_1std": round(mean + stdev,     2),
        "mean_plus_2std": round(mean + 2 * stdev, 2),
        "mean_plus_3std": round(mean + 3 * stdev, 2),
        "p50":  round(pct(50), 2),
        "p75":  round(pct(75), 2),
        "p90":  round(pct(90), 2),
        "p95":  round(pct(95), 2),
        "p99":  round(pct(99), 2),
        "min":  round(min(values), 2),
        "max":  round(max(values), 2),
        "n":    n,
    }


def recommend(all_stats):
    """
    Compare baseline (noise) vs breath scenarios
    to recommend thresholds for each mic.
    """
    result = {}
    for mic_key in ["mic1", "mic2"]:
        base = all_stats.get("baseline", {}).get(mic_key, {})
        mouth = all_stats.get("mouth_breathing", {}).get(mic_key, {})

        # Use whichever noise floor is higher (baseline or mouth breathing)
        noise_mean  = max(
            base.get("mean", 60),
            mouth.get("mean", 60)
        )
        noise_std   = max(
            base.get("std",  10),
            mouth.get("std",  10)
        )
        noise_p99   = max(
            base.get("p99", 80),
            mouth.get("p99", 80)
        )

        result[mic_key] = {
            "aggressive":   round(noise_mean + 1 * noise_std, 1),
            "recommended":  round(noise_mean + 2 * noise_std, 1),
            "conservative": round(noise_p99,  1),
            "note": (
                "aggressive=catches subtle breaths (more false positives). "
                "recommended=good balance. "
                "conservative=only clear breaths (fewest false positives). "
                "Apply to saved CSV during analysis only."
            )
        }
    return result


def build_results():
    all_stats = {}
    for scenario_id, readings in state.raw_data.items():
        m1_vals = [r["m1"] for r in readings]
        m2_vals = [r["m2"] for r in readings]
        all_stats[scenario_id] = {
            "mic1": calc_stats(m1_vals),
            "mic2": calc_stats(m2_vals),
            "n_samples": len(readings),
        }
    return all_stats, recommend(all_stats)


def save_results(all_stats, recommendations):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    ts      = int(time.time())
    pid     = state.participant_id

    json_filename = f"{OUTPUT_DIR}/thresholds_{pid}_{ts}.json"

    output = {
        "metadata": {
            "participant_id":  pid,
            "session_notes":   state.session_notes,
            "recorded_at":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "unix_timestamp":  ts,
            "n_scenarios":     len(SCENARIOS),
            "important_note": (
                "These thresholds are for POST-HOC ANALYSIS ONLY. "
                "Raw data recording never uses thresholds. "
                "Apply these during analysis of saved CSV files."
            ),
        },
        "recommendations": recommendations,
        "scenario_stats":  all_stats,
    }

    with open(json_filename, "w") as f:
        json.dump(output, f, indent=2)

    return json_filename


# ── SOCKET HANDLERS ───────────────────────────────────────

@socketio.on('get_scenarios')
def handle_get_scenarios():
    emit('scenarios', SCENARIOS)


@socketio.on('check_board')
def handle_check_board():
    port = find_xiao()
    if port:
        emit('board_status', {'connected': True, 'port': port})
    else:
        emit('board_status', {
            'connected': False,
            'message':   'XIAO not found — plug in USB cable'
        })


@socketio.on('start_calibration')
def handle_start(data):
    state.reset()
    state.participant_id = data.get('participant_id', f'P_{int(time.time())}')
    state.session_notes  = data.get('notes', '')
    state.start_time     = time.time()

    # Open serial
    port = find_xiao()
    if not port:
        emit('toast', 'XIAO not found — check USB connection')
        return

    state.serial_conn = serial.Serial(port, BAUD_RATE, timeout=2)
    time.sleep(2)
    state.serial_conn.reset_input_buffer()

    # Open CSV
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    ts  = int(time.time())
    pid = state.participant_id
    csv_path = f"{OUTPUT_DIR}/raw_{pid}_{ts}.csv"
    state.csv_file   = csv_path
    state.csv_handle = open(csv_path, "w", newline="")
    state.csv_writer = csv.writer(state.csv_handle)
    state.csv_writer.writerow([
        "host_time", "board_ms", "seq",
        "mic1", "mic2", "chip_temp_c", "scenario"
    ])

    # Start serial thread
    state.running = True
    t = threading.Thread(target=serial_read_loop, daemon=True)
    t.start()

    emit('toast', f'Recording started for {state.participant_id}')


@socketio.on('record_scenario')
def handle_record(data):
    state.current_scenario = data['scenario_id']


@socketio.on('stop_scenario')
def handle_stop_scenario(data):
    state.current_scenario = None


@socketio.on('finish_calibration')
def handle_finish():
    state.running          = False
    state.current_scenario = None

    # Close CSV
    if state.csv_handle:
        state.csv_handle.close()

    # Close serial
    if state.serial_conn and state.serial_conn.is_open:
        state.serial_conn.close()

    # Calculate and save
    all_stats, recommendations = build_results()
    json_file = save_results(all_stats, recommendations)

    emit('calibration_done', {
        'recommendations': recommendations,
        'csv_file':        state.csv_file,
        'json_file':       json_file,
    })


# ── ROUTES ────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template_string(HTML)


# ── MAIN ──────────────────────────────────────────────────

if __name__ == '__main__':
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    URL = f"http://localhost:{PORT}"

    print()
    print("═" * 54)
    print("  Nasal Monitor — Threshold Calibration Server")
    print("═" * 54)
    print()
    print("  ✅ Make sure XIAO is plugged in via USB")
    print()
    print("  🌐 Opening Chrome automatically...")
    print()
    print(f"  If Chrome doesn't open, go to:")
    print()
    print(f"       {URL}")
    print()
    print("  Press Ctrl+C to stop the server.")
    print()

    # Open Chrome automatically after 1.5s
    # (server needs a moment to start before browser connects)
    def open_browser():
        time.sleep(1.5)
        webbrowser.open(URL)

    threading.Thread(target=open_browser, daemon=True).start()

    socketio.run(app, host='0.0.0.0', port=PORT, debug=False)