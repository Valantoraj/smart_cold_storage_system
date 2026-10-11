"""
Unit tests for sim/model.py — refrigeration physics model.

Run with:  pytest edge/simulator/tests/test_model.py -v
"""

from __future__ import annotations

import random
from datetime import datetime, timezone, timedelta
from dataclasses import replace

import pytest

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

# We import from the package that sits two levels above this file.
# When running pytest from the simulator root the package is on sys.path.
import sys
import os

# Ensure the simulator root is importable regardless of how pytest is invoked.
_SIM_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _SIM_ROOT not in sys.path:
    sys.path.insert(0, _SIM_ROOT)

from sim.model import (
    DT_S,
    UnitState,
    ambient_c,
    apply_fault,
    repair,
    step,
)

SETPOINT = 4.0
FIXED_TS = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)  # noon UTC → ambient ~29°C


def _fresh_state(T: float = SETPOINT) -> UnitState:
    return UnitState(
        T=T,
        compressor_on=False,
        fault=None,
        RH=67.0,
        eff=1.0,
        seq=0,
        baseline_on_power_kw=2.0,
    )


def _run_steps(
    n: int,
    state: UnitState,
    setpoint: float = SETPOINT,
    ts: datetime = FIXED_TS,
    rng: random.Random | None = None,
) -> list[UnitState]:
    """Return a list of states after n steps (not including the initial state)."""
    if rng is None:
        rng = random.Random(42)
    states: list[UnitState] = []
    dt = timedelta(seconds=DT_S)
    for i in range(n):
        state = step(state, setpoint, ts + dt * i, rng)
        states.append(state)
    return states


def _steps_per_hour() -> int:
    return int(3600 / DT_S)


# ---------------------------------------------------------------------------
# 1. Healthy 6-hour simulation
# ---------------------------------------------------------------------------

class TestHealthySimulation:
    """Verify that a healthy unit over 6 simulated hours stays within expected bounds."""

    def test_duty_ratio_in_range(self):
        """Duty ratio (fraction of steps compressor is ON) should be 0.30–0.55.

        The exact duty depends on ambient temperature.  At a mild time of day
        (06:00 UTC, ambient ~24 °C) the thermostat cycles at roughly 35–45 %.
        At the heat peak (14:00 UTC, ambient ~29 °C) it can reach ~47 %.
        We use 06:00 UTC to keep the test deterministic and in a comfortable band.
        """
        n_steps = 6 * _steps_per_hour()
        # 06:00 UTC — ambient near daily mean (~24 °C), moderate duty expected
        ts_mild = datetime(2024, 6, 1, 6, 0, 0, tzinfo=timezone.utc)
        states = _run_steps(n_steps, _fresh_state(), ts=ts_mild, rng=random.Random(0))
        on_count = sum(1 for s in states if s.compressor_on)
        duty = on_count / n_steps
        assert 0.30 <= duty <= 0.55, f"Duty ratio {duty:.3f} outside [0.30, 0.55]"

    def test_temperature_within_setpoint_band(self):
        """Steady-state temperature should stay within setpoint ± 0.6 °C."""
        n_steps = 6 * _steps_per_hour()
        # Skip the first 10 minutes (warm-up / transient)
        warmup = int(10 * 60 / DT_S)
        states = _run_steps(n_steps, _fresh_state(), rng=random.Random(1))
        steady = states[warmup:]
        temps = [s.T for s in steady if s.T is not None]
        assert temps, "No temperature readings after warm-up"
        too_high = [t for t in temps if t > SETPOINT + 0.6]
        too_low = [t for t in temps if t < SETPOINT - 0.6]
        assert not too_high, (
            f"{len(too_high)} readings above setpoint+0.6; max={max(too_high):.3f}"
        )
        assert not too_low, (
            f"{len(too_low)} readings below setpoint-0.6; min={min(too_low):.3f}"
        )

    def test_seq_monotonically_increases(self):
        states = _run_steps(100, _fresh_state(), rng=random.Random(2))
        seqs = [s.seq for s in states]
        assert seqs == list(range(1, 101))

    def test_rh_within_reasonable_range(self):
        states = _run_steps(720, _fresh_state(), rng=random.Random(3))
        for s in states:
            assert 50.0 <= s.RH <= 85.0, f"RH {s.RH:.1f} out of expected range"


# ---------------------------------------------------------------------------
# 2. Compressor degradation fault
# ---------------------------------------------------------------------------

class TestCompressorDegradation:
    """After 12+ simulated minutes of degradation injection the unit should show
    rising temperature slope, higher duty, and higher on-power."""

    def _run_with_fault(self, fault_steps: int) -> tuple[list[UnitState], list[float]]:
        """
        Run fault_steps steps with degradation applied from step 0.
        Returns (states, power_kw_list).
        """
        state = _fresh_state()
        rng = random.Random(99)
        states: list[UnitState] = []
        powers: list[float] = []
        dt = timedelta(seconds=DT_S)

        for i in range(fault_steps):
            ts = FIXED_TS + dt * i
            state = step(state, SETPOINT, ts, rng)
            fault_elapsed_s = i * DT_S
            state = apply_fault(state, "compressor_degradation", fault_elapsed_s, ramp_min=10.0)

            if state.compressor_on:
                pwr = state.baseline_on_power_kw + rng.gauss(0.0, 0.05)
            else:
                pwr = 0.15 + rng.gauss(0.0, 0.02)
            powers.append(max(0.0, pwr))
            states.append(state)

        return states, powers

    def test_temperature_slope_positive_after_12_minutes(self):
        """15-minute window ending after 12 min of fault: slope >= 0.03 °C/min."""
        # 12 min of fault + extra for the 15-min window
        total_steps = int((12 + 15) * 60 / DT_S)
        states, _ = self._run_with_fault(total_steps)

        # Take the last 15-minute window
        window_steps = int(15 * 60 / DT_S)
        window = [s.T for s in states[-window_steps:] if s.T is not None]
        assert len(window) >= 2

        # Linear regression slope (simple)
        n = len(window)
        xs = list(range(n))
        x_mean = sum(xs) / n
        y_mean = sum(window) / n
        numerator = sum((xs[i] - x_mean) * (window[i] - y_mean) for i in range(n))
        denominator = sum((xs[i] - x_mean) ** 2 for i in range(n))
        slope_per_step = numerator / denominator if denominator != 0 else 0
        slope_per_min = slope_per_step * (60.0 / DT_S)
        assert slope_per_min >= 0.03, f"Temperature slope {slope_per_min:.4f} °C/min < 0.03"

    def test_duty_ratio_elevated(self):
        """Duty ratio with degradation for 12 min should be >= 1.3× baseline duty."""
        # Baseline duty (no fault)
        n_steps = int(12 * 60 / DT_S)
        baseline_states = _run_steps(n_steps, _fresh_state(), rng=random.Random(42))
        baseline_duty = sum(1 for s in baseline_states if s.compressor_on) / n_steps

        # Degraded duty
        degraded_states, _ = self._run_with_fault(n_steps)
        degraded_duty = sum(1 for s in degraded_states if s.compressor_on) / n_steps

        assert degraded_duty >= 1.3 * baseline_duty, (
            f"Degraded duty {degraded_duty:.3f} < 1.3× baseline {baseline_duty:.3f}"
        )

    def test_on_power_elevated(self):
        """Mean on-power with degradation should be >= 1.1× baseline on-power."""
        n_steps = int(12 * 60 / DT_S)

        # Baseline on-power
        baseline_states = _run_steps(n_steps, _fresh_state(), rng=random.Random(42))
        rng_b = random.Random(42)
        baseline_powers = []
        for s in baseline_states:
            if s.compressor_on:
                baseline_powers.append(s.baseline_on_power_kw + rng_b.gauss(0.0, 0.05))

        # Degraded on-power
        _, degraded_powers_all = self._run_with_fault(n_steps)
        degraded_states, _ = self._run_with_fault(n_steps)
        degraded_on_powers = [
            degraded_powers_all[i]
            for i, s in enumerate(degraded_states)
            if s.compressor_on
        ]

        if not baseline_powers or not degraded_on_powers:
            pytest.skip("Not enough compressor-on samples to compare power")

        mean_baseline = sum(baseline_powers) / len(baseline_powers)
        mean_degraded = sum(degraded_on_powers) / len(degraded_on_powers)

        assert mean_degraded >= 1.1 * mean_baseline, (
            f"Mean on-power: degraded={mean_degraded:.3f} < 1.1× baseline={mean_baseline:.3f}"
        )

    def test_temperature_below_safety_threshold(self):
        """Even with degradation for 12 min, temp should remain < 8.0 °C."""
        n_steps = int(12 * 60 / DT_S)
        states, _ = self._run_with_fault(n_steps)
        max_T = max(s.T for s in states if s.T is not None)
        assert max_T < 8.0, f"Temperature {max_T:.2f} °C exceeded safety threshold 8.0 °C"


# ---------------------------------------------------------------------------
# 3. Door-open fault
# ---------------------------------------------------------------------------

class TestDoorOpen:
    """RH should increase during door-open, and return to normal after 180 s."""

    def test_rh_increases_during_door_open(self):
        """RH should be higher with door open than without."""
        state = _fresh_state(T=SETPOINT)
        rng = random.Random(7)

        rh_values_door_open: list[float] = []
        for i in range(int(180 / DT_S)):
            ts = FIXED_TS + timedelta(seconds=i * DT_S)
            state = step(state, SETPOINT, ts, rng)
            fault_elapsed_s = i * DT_S
            state = apply_fault(state, "door_open", fault_elapsed_s)
            rh_values_door_open.append(state.RH)

        # Mean RH during door-open should be well above the healthy baseline of ~67
        mean_rh = sum(rh_values_door_open) / len(rh_values_door_open)
        assert mean_rh > 70.0, f"Mean RH {mean_rh:.1f}% not elevated during door open"

    def test_rh_returns_to_normal_after_180s(self):
        """After fault_elapsed_s > 180, apply_fault should not add the +15 RH boost."""
        state = _fresh_state(T=SETPOINT)
        # Apply fault well past 180 s
        state_after = apply_fault(state, "door_open", fault_elapsed_s=200.0)
        # RH should not have the +15 boost applied
        assert state_after.RH < 80.0, (
            f"RH {state_after.RH:.1f}% still elevated after door-open window closed"
        )

    def test_door_open_increases_temperature(self):
        """Door-open should cause a temperature rise compared to no fault."""
        state_nodoor = _fresh_state(T=SETPOINT)
        state_door = _fresh_state(T=SETPOINT)

        rng = random.Random(8)
        steps = int(120 / DT_S)  # 2 minutes
        for i in range(steps):
            ts = FIXED_TS + timedelta(seconds=i * DT_S)
            state_nodoor = step(state_nodoor, SETPOINT, ts, rng)
            state_door = step(replace(state_door, seq=state_door.seq), SETPOINT, ts, rng)
            state_door = apply_fault(state_door, "door_open", fault_elapsed_s=i * DT_S)

        assert state_door.T > state_nodoor.T, (
            "Door-open should result in higher temperature than no-fault"
        )


# ---------------------------------------------------------------------------
# 4. Sensor spike
# ---------------------------------------------------------------------------

class TestSensorSpike:
    """Exactly one sample at T=25.0, the next sample should be back to normal."""

    def test_spike_exactly_on_first_sample(self):
        state = _fresh_state(T=SETPOINT)
        rng = random.Random(5)

        # First application (fault_elapsed_s < DT_S) → spike
        ts = FIXED_TS
        state_after_step = step(state, SETPOINT, ts, rng)
        spiked = apply_fault(state_after_step, "sensor_spike", fault_elapsed_s=0.0)
        assert spiked.T == 25.0, f"Expected spike T=25.0, got {spiked.T}"

    def test_no_spike_on_subsequent_samples(self):
        state = _fresh_state(T=SETPOINT)
        rng = random.Random(5)
        ts = FIXED_TS

        state_after_step = step(state, SETPOINT, ts, rng)
        # Second application (fault_elapsed_s >= DT_S) → no spike
        not_spiked = apply_fault(state_after_step, "sensor_spike", fault_elapsed_s=DT_S)
        assert not_spiked.T != 25.0, (
            f"Expected normal temperature after spike, got {not_spiked.T}"
        )
        # Should be close to the stepped value (not 25°C)
        assert abs(not_spiked.T - SETPOINT) < 2.0, (
            f"Post-spike temperature {not_spiked.T:.2f} too far from setpoint"
        )

    def test_only_one_spike_in_sequence(self):
        """Over 10 steps, exactly one reading should be 25.0."""
        state = _fresh_state(T=SETPOINT)
        rng = random.Random(5)
        spike_count = 0
        fault_start = 0.0

        for i in range(10):
            ts = FIXED_TS + timedelta(seconds=i * DT_S)
            state = step(state, SETPOINT, ts, rng)
            fault_elapsed = (i * DT_S) - fault_start
            faulted = apply_fault(state, "sensor_spike", fault_elapsed_s=fault_elapsed)
            if faulted.T == 25.0:
                spike_count += 1
            # Update state only when not spiked (spike is just the reading, not physics)
            if faulted.T != 25.0:
                state = faulted

        assert spike_count == 1, f"Expected exactly 1 spike, got {spike_count}"


# ---------------------------------------------------------------------------
# 5. Sensor dropout
# ---------------------------------------------------------------------------

class TestSensorDropout:
    """apply_fault with sensor_dropout should return T=None."""

    def test_returns_none_temperature(self):
        state = _fresh_state(T=SETPOINT)
        dropped = apply_fault(state, "sensor_dropout", fault_elapsed_s=0.0)
        assert dropped.T is None, f"Expected T=None for sensor dropout, got {dropped.T}"

    def test_fault_label_set(self):
        state = _fresh_state(T=SETPOINT)
        dropped = apply_fault(state, "sensor_dropout", fault_elapsed_s=10.0)
        assert dropped.fault == "sensor_dropout"

    def test_other_fields_unchanged(self):
        state = _fresh_state(T=SETPOINT)
        state = replace(state, RH=72.5, eff=0.9, seq=42)
        dropped = apply_fault(state, "sensor_dropout", fault_elapsed_s=0.0)
        assert dropped.RH == 72.5
        assert dropped.eff == 0.9
        assert dropped.seq == 42


# ---------------------------------------------------------------------------
# 6. Ambient model sanity checks
# ---------------------------------------------------------------------------

class TestAmbientModel:
    def test_noon_warmer_than_midnight(self):
        midnight = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        noon = datetime(2024, 1, 1, 14, 0, 0, tzinfo=timezone.utc)
        assert ambient_c(noon) > ambient_c(midnight)

    def test_range_within_bounds(self):
        for hour in range(24):
            ts = datetime(2024, 6, 1, hour, 0, 0, tzinfo=timezone.utc)
            t = ambient_c(ts)
            assert 19.0 <= t <= 29.0, f"ambient_c at hour {hour} = {t:.2f} out of range"


# ---------------------------------------------------------------------------
# 7. Repair
# ---------------------------------------------------------------------------

class TestRepair:
    def test_eff_increases_toward_1(self):
        state = _fresh_state()
        state = replace(state, eff=0.5)
        for _ in range(20):
            state = repair(state)
        assert state.eff == 1.0

    def test_fault_cleared_when_fully_repaired(self):
        state = replace(_fresh_state(), eff=0.95, fault="compressor_degradation")
        state = repair(state)  # eff 0.95 → 1.0
        assert state.fault is None

    def test_fault_not_cleared_while_still_degraded(self):
        state = replace(_fresh_state(), eff=0.5, fault="compressor_degradation")
        state = repair(state)  # eff 0.5 → 0.55
        assert state.fault == "compressor_degradation"
