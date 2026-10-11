"""
sim/model.py — Physics-based refrigeration model
==================================================
Pure functions, no I/O, deterministic with a seed.
Used by the simulator main loop and by the backfill generator.

Step dt = 5 s.
"""

from __future__ import annotations
import math
import random
from dataclasses import dataclass, field
from typing import Optional

# ── Constants ────────────────────────────────────────────────────────────────
DT_S        = 5          # simulation step seconds
DT_MIN      = DT_S / 60  # step in minutes
K_LEAK      = 0.01       # °C/min per °C delta (ambient − internal)
K_COOL      = 0.50       # °C/min cooling when compressor ON (×eff)
HYST_ON     = 0.25       # thermostat hysteresis ON threshold above setpoint
HYST_OFF    = 0.25       # thermostat hysteresis OFF threshold below setpoint
NOISE_SIGMA = 0.02       # °C per step Gaussian noise
POWER_OFF   = 0.15       # kW when compressor OFF (fans)
POWER_ON    = 2.0        # kW base when ON (healthy)
POWER_NOISE = 0.05
HUMIDITY_BASE   = 67.0
HUMIDITY_NOISE  = 1.0
FAULT_RAMP_MIN  = 10     # minutes to decay eff from 1.0 → 0.20 for compressor_degradation
REPAIR_RAMP_MIN = 1      # minutes to restore eff to 1.0


@dataclass
class UnitState:
    unit_id:        str
    setpoint_c:     float
    hard_limit_c:   float
    temp_c:         float = 0.0
    humidity_pct:   float = HUMIDITY_BASE
    compressor_on:  bool  = False
    eff:            float = 1.0          # compressor efficiency (1.0 = healthy)
    power_kw:       float = POWER_OFF
    fault:          Optional[str] = None # active fault name
    fault_elapsed_min: float = 0.0
    hum_drift_rate: float = 0.0          # °C/min humidity drift
    spike_pending:  bool  = False        # emit one spike on next step
    dropout_remaining_s: float = 0.0    # suppress output for this many seconds
    seq:            int   = 0
    rng:            random.Random = field(default_factory=random.Random)

    def __post_init__(self):
        self.temp_c = self.setpoint_c + self.rng.gauss(0, 0.1)

    def seed(self, s: int):
        self.rng.seed(s)


def ambient_temp(unix_ts: float) -> float:
    """Diurnal ambient: 24 + 5·sin(2π·(hour/24 − 0.25))"""
    hour = (unix_ts % 86400) / 3600
    return 24.0 + 5.0 * math.sin(2 * math.pi * (hour / 24.0 - 0.25))


def step(state: UnitState, unix_ts: float) -> Optional[dict]:
    """
    Advance simulation by one DT step.
    Returns a raw sample dict or None (dropout).
    """
    rng = state.rng

    # ── Dropout suppression ──────────────────────────────────────────────────
    if state.dropout_remaining_s > 0:
        state.dropout_remaining_s = max(0.0, state.dropout_remaining_s - DT_S)
        return None

    # ── Fault ramp / repair ──────────────────────────────────────────────────
    if state.fault == "compressor_degradation":
        state.fault_elapsed_min += DT_MIN
        progress = min(1.0, state.fault_elapsed_min / FAULT_RAMP_MIN)
        state.eff = 1.0 - 0.80 * progress     # 1.0 → 0.20
    elif state.fault == "repair":
        state.fault_elapsed_min += DT_MIN
        progress = min(1.0, state.fault_elapsed_min / REPAIR_RAMP_MIN)
        state.eff = 0.20 + 0.80 * progress    # 0.20 → 1.0
        if progress >= 1.0:
            state.fault = None
            state.fault_elapsed_min = 0.0
    elif state.fault == "door_open":
        state.fault_elapsed_min += DT_MIN
        if state.fault_elapsed_min >= 3.0:    # auto-clear after 3 min
            state.fault = None
            state.fault_elapsed_min = 0.0
            state.hum_drift_rate = 0.0
    elif state.fault == "humidity_drift":
        state.hum_drift_rate = 0.5            # +0.5 pct/min

    # ── Thermostat ───────────────────────────────────────────────────────────
    if state.temp_c >= state.setpoint_c + HYST_ON:
        state.compressor_on = True
    elif state.temp_c <= state.setpoint_c - HYST_OFF:
        state.compressor_on = False

    # ── Temperature physics ──────────────────────────────────────────────────
    A = ambient_temp(unix_ts)
    door_factor = 5.0 if state.fault == "door_open" else 1.0
    leak   = K_LEAK * door_factor * (A - state.temp_c) * DT_MIN
    cool   = K_COOL * state.eff * DT_MIN if state.compressor_on else 0.0
    noise  = rng.gauss(0, NOISE_SIGMA)
    state.temp_c += leak - cool + noise

    # ── Humidity ─────────────────────────────────────────────────────────────
    door_hum = 15.0 if state.fault == "door_open" else 0.0
    state.humidity_pct += state.hum_drift_rate * DT_MIN + rng.gauss(0, HUMIDITY_NOISE * DT_MIN)
    state.humidity_pct += door_hum * DT_MIN
    state.humidity_pct = max(0.0, min(100.0, state.humidity_pct))

    # ── Power ────────────────────────────────────────────────────────────────
    if state.compressor_on:
        state.power_kw = POWER_ON * (1.0 + 0.5 * (1.0 - state.eff)) + rng.gauss(0, POWER_NOISE)
    else:
        state.power_kw = POWER_OFF + rng.gauss(0, 0.02)
    state.power_kw = max(0.0, state.power_kw)

    # ── Spike fault ──────────────────────────────────────────────────────────
    reported_temp = state.temp_c
    if state.spike_pending:
        reported_temp = 25.0
        state.spike_pending = False
        state.fault = None
        state.fault_elapsed_min = 0.0

    state.seq += 1
    return {
        "schema":         "v1",
        "unit_id":        state.unit_id,
        "ts":             _iso(unix_ts),
        "seq":            state.seq,
        "temp_c":         round(reported_temp, 3),
        "humidity_pct":   round(state.humidity_pct, 2),
        "compressor_on":  state.compressor_on,
        "power_kw":       round(state.power_kw, 3),
        "door_open":      state.fault == "door_open",
    }


def apply_command(state: UnitState, cmd: dict) -> None:
    """Apply a control command to unit state."""
    action = cmd.get("cmd", "")
    if action == "inject":
        fault = cmd.get("fault", "")
        state.fault = fault
        state.fault_elapsed_min = 0.0
        if fault == "sensor_spike":
            state.spike_pending = True
            state.fault = None
        elif fault == "sensor_dropout":
            state.dropout_remaining_s = 90.0
            state.fault = None
        elif fault == "humidity_drift":
            state.hum_drift_rate = 0.5
    elif action == "repair":
        state.fault = "repair"
        state.fault_elapsed_min = 0.0
        state.hum_drift_rate = 0.0
        state.spike_pending = False
        state.dropout_remaining_s = 0.0
    elif action == "set":
        pass  # handled by caller (e.g. interval_s)


def _iso(unix_ts: float) -> str:
    import datetime
    return datetime.datetime.fromtimestamp(unix_ts,
           tz=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
