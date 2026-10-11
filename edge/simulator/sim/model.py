"""
Refrigeration physics model for the cold-twin simulator.

Pure module: no I/O, no side effects, no global mutable state.
All randomness is injected via an explicit random.Random instance.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DT_S: float = 5.0            # simulation time-step, seconds
K_LEAK: float = 0.01         # thermal leak coefficient  (°C/s per °C delta)
COOLING_PER_MIN: float = 0.50 # cooling capacity (°C/min) at full efficiency
FAN_POWER: float = 0.15      # fan-only power draw (kW)
ON_POWER_BASE: float = 2.0   # base compressor power draw (kW)
NOISE_SIGMA: float = 0.02    # temperature Gaussian noise (°C/step)

# Derived convenience
_DT_MIN: float = DT_S / 60.0  # DT expressed in minutes


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

@dataclass
class UnitState:
    """Immutable-style snapshot of one cold-storage unit."""

    T: float                        # current temperature (°C)
    compressor_on: bool             # compressor running flag
    fault: Optional[str]            # active fault name, or None
    RH: float                       # relative humidity (%)
    eff: float                      # compressor efficiency 0–1
    seq: int                        # monotonic sequence counter
    baseline_on_power_kw: float     # reference on-power for this unit


# ---------------------------------------------------------------------------
# Ambient temperature model
# ---------------------------------------------------------------------------

def ambient_c(ts_utc: datetime) -> float:
    """Return ambient temperature (°C) as a sinusoidal function of time-of-day.

    Peaks at 14:00 UTC (≈ hottest part of day) and troughs at 02:00 UTC.
    Formula: 24 + 5 * sin(2π * (hour_of_day / 24 - 0.25))
    """
    hour_fraction = (ts_utc.hour + ts_utc.minute / 60.0 + ts_utc.second / 3600.0)
    return 24.0 + 5.0 * math.sin(2.0 * math.pi * (hour_fraction / 24.0 - 0.25))


# ---------------------------------------------------------------------------
# Physics step
# ---------------------------------------------------------------------------

def step(
    state: UnitState,
    setpoint_c: float,
    ts_utc: datetime,
    rng: random.Random,
) -> UnitState:
    """Advance the unit state by one DT_S time-step.

    Thermostat hysteresis:
      - Compressor turns ON  when T >= setpoint + 0.25
      - Compressor turns OFF when T <= setpoint - 0.25
      (stays in current state between those thresholds)

    Temperature evolution (per-minute rate, then scaled by DT_MIN):
      dT/dt = k_leak*(ambient - T)  [thermal leak]
             - cooling_per_min * eff * compressor_on  [active cooling]
             + N(0, NOISE_SIGMA)  [sensor / thermal noise]

    Power:
      - OFF state: FAN_POWER ± 0.02 kW
      - ON  state: ON_POWER_BASE * (1 + 0.5*(1 - eff)) ± 0.05 kW

    RH:
      - Base 67% + N(0, 1) noise
      - Slightly lower (-2%) when compressor is running
    """
    amb = ambient_c(ts_utc)

    # --- Thermostat ---
    new_compressor_on = state.compressor_on
    if state.T >= setpoint_c + 0.25:
        new_compressor_on = True
    elif state.T <= setpoint_c - 0.25:
        new_compressor_on = False

    # --- Temperature update (rate in °C/min, scaled to step) ---
    leak_rate = K_LEAK * (amb - state.T)          # °C/min
    cool_rate = COOLING_PER_MIN * state.eff * (1.0 if new_compressor_on else 0.0)
    noise = rng.gauss(0.0, NOISE_SIGMA)
    dT = (leak_rate - cool_rate) * _DT_MIN + noise
    new_T = state.T + dT

    # --- Power draw ---
    if new_compressor_on:
        new_power = ON_POWER_BASE * (1.0 + 0.5 * (1.0 - state.eff)) + rng.gauss(0.0, 0.05)
    else:
        new_power = FAN_POWER + rng.gauss(0.0, 0.02)
    new_power = max(0.0, new_power)

    # --- Relative humidity ---
    rh_noise = rng.gauss(0.0, 1.0)
    if new_compressor_on:
        new_RH = 67.0 - 2.0 + rh_noise
    else:
        new_RH = 67.0 + rh_noise
    new_RH = max(0.0, min(100.0, new_RH))

    return replace(
        state,
        T=new_T,
        compressor_on=new_compressor_on,
        # power_kw is carried externally via the published payload; stored in
        # baseline_on_power_kw only when compressor is on for fault detection
        baseline_on_power_kw=(new_power if new_compressor_on else state.baseline_on_power_kw),
        RH=new_RH,
        seq=state.seq + 1,
    )


# ---------------------------------------------------------------------------
# Fault injection
# ---------------------------------------------------------------------------

def apply_fault(
    state: UnitState,
    fault: str,
    fault_elapsed_s: float,
    ramp_min: float = 10.0,
) -> UnitState:
    """Return a new UnitState with fault effects applied.

    Parameters
    ----------
    state:            current unit state (already updated by step())
    fault:            fault name string
    fault_elapsed_s:  seconds since the fault was first injected
    ramp_min:         ramp duration in *real* minutes for degradation faults

    Supported faults
    ----------------
    compressor_degradation
        Efficiency decays linearly from 1.0 → 0.20 over ``ramp_min`` minutes.

    door_open
        For the first 180 s: k_leak multiplied by 5, RH +15 percentage points.
        After 180 s the door is assumed closed; state returns to normal
        (caller is responsible for clearing the fault after 180 s if desired).

    humidity_drift
        RH increases by 0.5 per *simulated* minute (0.5 * DT_MIN per step)
        up to a maximum of 95%.

    sensor_spike
        Returns T = 25.0 for exactly one sample (first call after injection).
        Subsequent calls are unaffected (caller tracks elapsed).

    sensor_dropout
        Returns a sentinel state with T = None (caller must handle None).
    """
    if fault == "compressor_degradation":
        ramp_s = ramp_min * 60.0
        progress = min(fault_elapsed_s / ramp_s, 1.0)
        new_eff = 1.0 - (1.0 - 0.20) * progress  # 1.0 → 0.20
        return replace(state, fault=fault, eff=new_eff)

    elif fault == "door_open":
        if fault_elapsed_s <= 180.0:
            # Simulate increased thermal leak and humidity ingress
            amb = 24.0  # approximate; caller can pass a better value if needed
            leak_extra = K_LEAK * 5.0 * (amb - state.T) * _DT_MIN
            new_T = state.T + leak_extra
            new_RH = min(100.0, state.RH + 15.0)
            return replace(state, fault=fault, T=new_T, RH=new_RH)
        else:
            # Door closed again — remove fault effect (but keep fault label
            # so caller knows it happened; caller clears fault if desired)
            return replace(state, fault=fault)

    elif fault == "humidity_drift":
        drift_per_step = 0.5 * _DT_MIN  # 0.5 %/min scaled to step
        new_RH = min(95.0, state.RH + drift_per_step)
        return replace(state, fault=fault, RH=new_RH)

    elif fault == "sensor_spike":
        # Only the very first sample after injection returns the spike value
        if fault_elapsed_s < DT_S:
            return replace(state, fault=fault, T=25.0)
        # Subsequent samples are normal
        return replace(state, fault=fault)

    elif fault == "sensor_dropout":
        # Signal dropout: T is set to None as a sentinel.
        # The type annotation allows this via Optional usage in callers.
        return replace(state, fault=fault, T=None)  # type: ignore[arg-type]

    else:
        raise ValueError(f"Unknown fault: {fault!r}")


# ---------------------------------------------------------------------------
# Repair
# ---------------------------------------------------------------------------

def repair(state: UnitState) -> UnitState:
    """Begin gradual restoration of compressor efficiency toward 1.0.

    Each call nudges eff up by 0.05 (i.e., full recovery in ~16 steps / ~80 s).
    Clears the active fault once eff reaches 1.0.
    """
    new_eff = min(1.0, state.eff + 0.05)
    new_fault = state.fault if new_eff < 1.0 else None
    return replace(state, eff=new_eff, fault=new_fault)
