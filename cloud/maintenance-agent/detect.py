"""
detect.py — Cloud-side fog rule replication
============================================
Mirrors the fog node threshold/PM logic so the cloud agent can
evaluate units using only BigQuery data, without calling the edge.

All thresholds come from config/rules.json and config/units.json.
"""

from __future__ import annotations
import json
from dataclasses import dataclass, field
from typing import Optional

# ── Default config (overridden by load_config()) ────────────────────────────
_RULES: dict = {
    "pm": {"slope_c_per_min": 0.03, "duty_ratio": 1.30, "on_power_ratio": 1.10,
           "consecutive_evals": 3},
    "temp_critical": {"over_hard_limit_min": 2},
    "humidity": {"out_of_range_min": 5},
    "baseline_duty": 0.40,
}
_UNITS: dict = {
    "CS-01": {"setpoint_c": 4.0, "hard_limit_c": 8.0, "humidity_range": [55, 85]},
    "CS-02": {"setpoint_c": 4.0, "hard_limit_c": 8.0, "humidity_range": [55, 85]},
    "CS-03": {"setpoint_c": 5.0, "hard_limit_c": 8.0, "humidity_range": [55, 85]},
}


def load_config(rules_path: str = "/app/config/rules.json",
                units_path: str = "/app/config/units.json") -> None:
    """Load runtime config. Silently uses defaults if files absent."""
    global _RULES, _UNITS
    try:
        with open(rules_path) as f:
            _RULES = json.load(f)
    except FileNotFoundError:
        pass
    try:
        with open(units_path) as f:
            _UNITS = json.load(f)
    except FileNotFoundError:
        pass


# ── Data structures ──────────────────────────────────────────────────────────

@dataclass
class TelemetryWindow:
    """Last N minutes of telemetry for one unit."""
    unit_id: str
    rows: list[dict]           # sorted by ts ascending, newest last

    @property
    def latest(self) -> Optional[dict]:
        return self.rows[-1] if self.rows else None

    @property
    def empty(self) -> bool:
        return len(self.rows) == 0


@dataclass
class DetectionResult:
    unit_id: str
    health_state: str          # OK | WARNING | CRITICAL
    triggers: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "unit_id": self.unit_id,
            "health_state": self.health_state,
            "triggers": self.triggers,
            "details": self.details,
        }


# ── Detection functions ──────────────────────────────────────────────────────

def _unit_cfg(unit_id: str) -> dict:
    return _UNITS.get(unit_id, _UNITS.get("CS-01"))


def check_temperature(window: TelemetryWindow) -> tuple[bool, dict]:
    """Return (critical, details). Critical = hard limit exceeded."""
    if window.empty:
        return False, {}
    cfg = _unit_cfg(window.unit_id)
    hard_limit = cfg.get("hard_limit_c", 8.0)
    over_limit_min = _RULES.get("temp_critical", {}).get("over_hard_limit_min", 2)

    # Count consecutive minutes over hard limit (newest N rows)
    breach_count = 0
    for row in reversed(window.rows):
        if row.get("temp_avg_c", 0) > hard_limit:
            breach_count += 1
        else:
            break

    critical = breach_count >= over_limit_min
    latest_temp = window.latest.get("temp_avg_c") if window.latest else None
    return critical, {
        "temp_avg_c": latest_temp,
        "hard_limit_c": hard_limit,
        "breach_minutes": breach_count,
        "critical": critical,
    }


def check_pm_warning(window: TelemetryWindow) -> tuple[bool, dict]:
    """Return (pm_warning, details). PM = predictive maintenance signal."""
    if len(window.rows) < 3:
        return False, {}

    cfg = _unit_cfg(window.unit_id)
    pm = _RULES.get("pm", {})
    slope_thresh = pm.get("slope_c_per_min", 0.03)
    duty_ratio   = pm.get("duty_ratio", 1.30)
    power_ratio  = pm.get("on_power_ratio", 1.10)
    consec       = pm.get("consecutive_evals", 3)
    base_duty    = _RULES.get("baseline_duty", 0.40)
    # Estimate baseline on-power from first half of window
    half = max(1, len(window.rows) // 2)
    base_powers = [r.get("on_power_avg_kw", 2.0) for r in window.rows[:half] if r.get("on_power_avg_kw")]
    base_power = sum(base_powers) / len(base_powers) if base_powers else 2.0

    # Check last `consec` rows
    tail = window.rows[-consec:]
    slope_ok = all(r.get("temp_slope_c_per_min", 0) >= slope_thresh for r in tail)
    duty_ok  = all(r.get("compressor_duty", 0) >= base_duty * duty_ratio for r in tail)
    power_ok = all(r.get("on_power_avg_kw", 0) >= base_power * power_ratio for r in tail)

    triggered = slope_ok and duty_ok and power_ok
    latest = window.latest or {}
    return triggered, {
        "slope_c_per_min": latest.get("temp_slope_c_per_min"),
        "compressor_duty": latest.get("compressor_duty"),
        "on_power_avg_kw": latest.get("on_power_avg_kw"),
        "base_duty_threshold": round(base_duty * duty_ratio, 3),
        "base_power_threshold": round(base_power * power_ratio, 3),
        "consecutive_evals_checked": consec,
        "pm_warning": triggered,
    }


def check_humidity(window: TelemetryWindow) -> tuple[bool, dict]:
    """Return (humidity_alert, details)."""
    if window.empty:
        return False, {}
    cfg = _unit_cfg(window.unit_id)
    lo, hi = cfg.get("humidity_range", [55, 85])
    out_range_min = _RULES.get("humidity", {}).get("out_of_range_min", 5)

    breach_count = 0
    for row in reversed(window.rows):
        h = row.get("humidity_avg_pct", 70)
        if h < lo or h > hi:
            breach_count += 1
        else:
            break

    alert = breach_count >= out_range_min
    latest_h = window.latest.get("humidity_avg_pct") if window.latest else None
    return alert, {
        "humidity_avg_pct": latest_h,
        "range": [lo, hi],
        "breach_minutes": breach_count,
        "alert": alert,
    }


def check_dropout(window: TelemetryWindow, max_gap_min: int = 5) -> tuple[bool, dict]:
    """Return (dropout, details). Dropout = no data in last max_gap_min minutes."""
    if window.empty:
        return True, {"gap_minutes": "unknown", "dropout": True}

    from datetime import datetime, timezone
    latest_ts_str = window.latest.get("ts", "")
    try:
        latest_ts = datetime.fromisoformat(latest_ts_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        gap_min = (now - latest_ts).total_seconds() / 60
        dropout = gap_min > max_gap_min
        return dropout, {"gap_minutes": round(gap_min, 1), "latest_ts": latest_ts_str,
                         "dropout": dropout}
    except Exception:
        return False, {"gap_minutes": None}


def evaluate_unit(window: TelemetryWindow) -> DetectionResult:
    """Full evaluation of one unit — returns DetectionResult."""
    triggers = []
    details = {}

    # Dropout check
    dropped, d = check_dropout(window)
    details["dropout"] = d
    if dropped:
        triggers.append("SENSOR_DROPOUT")

    # Temperature / critical
    crit, d = check_temperature(window)
    details["temperature"] = d
    if crit:
        triggers.append("TEMP_CRITICAL")

    # PM warning
    pm, d = check_pm_warning(window)
    details["pm"] = d
    if pm:
        triggers.append("PM_WARNING")

    # Humidity
    hum, d = check_humidity(window)
    details["humidity"] = d
    if hum:
        triggers.append("HUMIDITY_ALERT")

    # Derive health state
    if "TEMP_CRITICAL" in triggers:
        state = "CRITICAL"
    elif any(t in triggers for t in ["PM_WARNING", "HUMIDITY_ALERT"]):
        state = "WARNING"
    elif "SENSOR_DROPOUT" in triggers:
        state = "WARNING"
    else:
        state = "OK"

    # Override with latest reported state if available
    if window.latest:
        reported = window.latest.get("health_state", state)
        if reported == "CRITICAL":
            state = "CRITICAL"

    return DetectionResult(
        unit_id=window.unit_id,
        health_state=state,
        triggers=triggers,
        details=details,
    )
