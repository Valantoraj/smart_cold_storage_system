"""
decide.py — Deterministic fallback decision engine
===================================================
Used when the LLM (Gemini) is unavailable or returns an unusable response.
Produces the same JSON structure as the LLM tool-calling path so the
caller doesn't need to branch.
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
import uuid


# ── Decision schema ──────────────────────────────────────────────────────────

def make_decision(
    unit_id: str,
    health_state: str,
    triggers: list[str],
    details: dict,
    open_work_orders: list[dict],
) -> dict:
    """
    Produce a maintenance decision dict deterministically.

    Returns:
        {
          "unit_id": str,
          "action": str,          # "no_action" | "create_work_order" | "escalate"
          "urgency": str,         # "low" | "medium" | "high" | "critical"
          "description": str,
          "work_order_id": str | None,
          "reasoning": str,
          "source": "deterministic"
        }
    """
    # Don't duplicate open work orders for same unit
    has_open_wo = any(
        wo.get("unit_id") == unit_id and wo.get("status") == "open"
        for wo in open_work_orders
    )

    # ── CRITICAL temperature ──────────────────────────────────────────────
    if "TEMP_CRITICAL" in triggers:
        temp_d = details.get("temperature", {})
        temp = temp_d.get("temp_avg_c", "?")
        limit = temp_d.get("hard_limit_c", 8.0)
        breach = temp_d.get("breach_minutes", "?")

        if has_open_wo:
            return _decision(unit_id, "escalate", "critical",
                f"TEMP_CRITICAL: {temp}°C > {limit}°C for {breach} min. "
                f"Existing work order — escalating to critical.",
                reasoning="Temperature hard limit exceeded with existing WO — escalate.")

        wo_id = _new_wo_id()
        return _decision(unit_id, "create_work_order", "critical",
            f"Temperature critically high: {temp}°C (limit {limit}°C) "
            f"for {breach} consecutive minutes. Immediate inspection required.",
            work_order_id=wo_id,
            reasoning="Temp above hard limit for required duration → CRITICAL work order.")

    # ── PM warning (compressor degradation) ──────────────────────────────
    if "PM_WARNING" in triggers:
        pm_d = details.get("pm", {})
        slope = pm_d.get("slope_c_per_min", "?")
        duty  = pm_d.get("compressor_duty", "?")
        power = pm_d.get("on_power_avg_kw", "?")

        if has_open_wo:
            return _decision(unit_id, "no_action", "medium",
                f"PM_WARNING active (slope={slope}, duty={duty}, power={power}kW) "
                f"but work order already open — monitoring.",
                reasoning="PM_WARNING with existing WO — avoid duplicate.")

        wo_id = _new_wo_id()
        return _decision(unit_id, "create_work_order", "high",
            f"Predictive maintenance signal: temp slope {slope}°C/min, "
            f"compressor duty {duty:.0%} (elevated), on-power {power}kW. "
            f"Schedule compressor inspection within 48h. Check refrigerant and condenser coils.",
            work_order_id=wo_id,
            reasoning="All 3 PM thresholds exceeded for required consecutive evals.")

    # ── Humidity alert ────────────────────────────────────────────────────
    if "HUMIDITY_ALERT" in triggers:
        hum_d = details.get("humidity", {})
        h = hum_d.get("humidity_avg_pct", "?")
        lo, hi = hum_d.get("range", [55, 85])

        if has_open_wo:
            return _decision(unit_id, "no_action", "low",
                f"HUMIDITY_ALERT ({h}% outside [{lo},{hi}]%) — existing WO open.",
                reasoning="Humidity alert suppressed by existing work order.")

        wo_id = _new_wo_id()
        return _decision(unit_id, "create_work_order", "medium",
            f"Humidity out of range: {h}% (normal {lo}–{hi}%). "
            f"Check drain line, door seals, and dehumidifier.",
            work_order_id=wo_id,
            reasoning="Humidity persistently out of range → medium priority WO.")

    # ── Sensor dropout ────────────────────────────────────────────────────
    if "SENSOR_DROPOUT" in triggers:
        gap = details.get("dropout", {}).get("gap_minutes", "?")
        return _decision(unit_id, "create_work_order", "medium",
            f"No telemetry for {gap} minutes. Check edge node connectivity, "
            f"sensor power, and MQTT broker.",
            work_order_id=_new_wo_id(),
            reasoning="Data gap exceeds threshold — connectivity investigation needed.")

    # ── All OK ────────────────────────────────────────────────────────────
    return _decision(unit_id, "no_action", "low",
        f"Unit {unit_id} operating normally (health_state={health_state}). No action required.",
        reasoning="No triggers detected.")


def _new_wo_id() -> str:
    return f"WO-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M')}-{uuid.uuid4().hex[:6].upper()}"


def _decision(
    unit_id: str,
    action: str,
    urgency: str,
    description: str,
    work_order_id: Optional[str] = None,
    reasoning: str = "",
) -> dict:
    return {
        "unit_id": unit_id,
        "action": action,
        "urgency": urgency,
        "description": description,
        "work_order_id": work_order_id,
        "reasoning": reasoning,
        "source": "deterministic",
    }
