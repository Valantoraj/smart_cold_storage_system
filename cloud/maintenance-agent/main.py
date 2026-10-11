"""
maintenance-agent — Cloud Run (Phase 4.4)
==========================================
Runs a Gemini-powered agentic maintenance cycle over all cold storage units.
Uses function calling to query BigQuery, then decides whether to create work orders.

POST /run-cycle        — trigger one maintenance cycle (called by Cloud Scheduler)
POST /admin/retrain    — placeholder for BQML retrain trigger
GET  /healthz          — health check
GET  /last-run         — returns last agent_runs row summary
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, BackgroundTasks, Response
from fastapi.responses import JSONResponse
from google.cloud import bigquery

from detect import TelemetryWindow, evaluate_unit, load_config
from decide import make_decision

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("maintenance-agent")

# ── Config ────────────────────────────────────────────────────────────────────
PROJECT_ID   = os.environ.get("GCP_PROJECT_ID", "project-f47e3be0-07f0-4225-b8e")
DATASET      = os.environ.get("BQ_DATASET",     "coldstorage")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL",   "gemini-3.5-flash")
LOCATION     = os.environ.get("GEMINI_LOCATION","global")
WINDOW_MIN   = int(os.environ.get("WINDOW_MIN", "30"))
VALID_UNITS  = ["CS-01", "CS-02", "CS-03"]

app = FastAPI(title="cold-twin maintenance-agent", version="1.0.0")
bq  = bigquery.Client(project=PROJECT_ID)

load_config()  # load rules/units from /app/config if available

_last_run_summary: dict = {}


# ── BigQuery helpers ─────────────────────────────────────────────────────────

def _q(sql: str) -> list[dict]:
    """Run a BQ query and return rows as list of dicts."""
    rows = list(bq.query(sql).result())
    return [dict(r) for r in rows]


def _table(name: str) -> str:
    return f"`{PROJECT_ID}.{DATASET}.{name}`"


# ── Agent tools (callable by Gemini via function calling) ────────────────────

def get_unit_status(unit_id: str) -> dict:
    """Get the latest telemetry row and health state for a unit."""
    sql = f"""
        SELECT ts, unit_id, temp_avg_c, humidity_avg_pct,
               compressor_duty, power_avg_kw, on_power_avg_kw,
               temp_slope_c_per_min, health_state, health_score
        FROM {_table('telemetry_1min')}
        WHERE unit_id = '{unit_id}'
        ORDER BY ts DESC
        LIMIT 1
    """
    rows = _q(sql)
    if not rows:
        return {"unit_id": unit_id, "error": "no_data"}
    r = rows[0]
    return {k: (str(v) if isinstance(v, datetime) else v) for k, v in r.items()}


def get_trend(unit_id: str, minutes: int = 30) -> dict:
    """Get telemetry trend for a unit over the last N minutes."""
    sql = f"""
        SELECT ts, temp_avg_c, compressor_duty, power_avg_kw,
               on_power_avg_kw, temp_slope_c_per_min, health_state
        FROM {_table('telemetry_1min')}
        WHERE unit_id = '{unit_id}'
          AND ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {minutes} MINUTE)
        ORDER BY ts ASC
    """
    rows = _q(sql)
    # Summarise the trend
    if not rows:
        return {"unit_id": unit_id, "minutes": minutes, "rows": 0, "error": "no_data"}
    temps  = [r["temp_avg_c"]           for r in rows if r.get("temp_avg_c")           is not None]
    duties = [r["compressor_duty"]      for r in rows if r.get("compressor_duty")      is not None]
    powers = [r["on_power_avg_kw"]      for r in rows if r.get("on_power_avg_kw")      is not None]
    slopes = [r["temp_slope_c_per_min"] for r in rows if r.get("temp_slope_c_per_min") is not None]
    def _avg(lst): return round(sum(lst)/len(lst), 3) if lst else None
    def _rnd(v):   return round(v, 3) if v is not None else None
    return {
        "unit_id":             unit_id,
        "minutes":             minutes,
        "rows":                len(rows),
        "temp_min_c":          _rnd(min(temps))  if temps  else None,
        "temp_max_c":          _rnd(max(temps))  if temps  else None,
        "temp_avg_c":          _avg(temps),
        "temp_slope_avg":      _avg(slopes),
        "compressor_duty_avg": _avg(duties),
        "on_power_avg_kw":     _avg(powers),
        "health_states":       list({r["health_state"] for r in rows if r.get("health_state")}),
    }


def get_anomalies(unit_id: str, hours: int = 6) -> dict:
    """Get recent anomaly detection results for a unit."""
    sql = f"""
        SELECT ts, metric, is_anomaly, anomaly_prob, actual_value,
               lower_bound, upper_bound
        FROM {_table('anomaly_results')}
        WHERE unit_id = '{unit_id}'
          AND ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {hours} HOUR)
          AND is_anomaly = TRUE
        ORDER BY ts DESC
        LIMIT 10
    """
    rows = _q(sql)
    return {
        "unit_id":        unit_id,
        "hours":          hours,
        "anomaly_count":  len(rows),
        "anomalies":      [{k: (str(v) if isinstance(v, datetime) else v)
                            for k, v in r.items()} for r in rows],
    }


def search_runbook(fault_code: str) -> dict:
    """Return runbook guidance for a known fault code."""
    runbook = {
        "compressor_degradation": {
            "symptoms": "Temp rising, duty >65%, on-power elevated, all signals rising for 10+ min.",
            "action":   "Schedule compressor inspection within 48h. Check refrigerant. Clean condenser coils.",
            "urgency":  "high",
        },
        "door_open": {
            "symptoms": "Temp and humidity spike simultaneously within 2-3 min.",
            "action":   "Check door immediately. Inspect door seal. Not an equipment fault.",
            "urgency":  "medium",
        },
        "sensor_spike": {
            "symptoms": "Single reading far outside normal range, immediately returns to normal.",
            "action":   "Flag reading as suspect. Monitor for recurrence. If repeated, replace sensor.",
            "urgency":  "low",
        },
        "humidity_drift": {
            "symptoms": "Humidity climbing gradually over 30+ min. Temperature normal.",
            "action":   "Check drain line. Inspect door seals. Service dehumidifier.",
            "urgency":  "medium",
        },
        "sensor_dropout": {
            "symptoms": "No readings for 60-90 seconds from one unit.",
            "action":   "Check edge node connectivity. Verify sensor power. Check MQTT broker.",
            "urgency":  "medium",
        },
        "pm_warning": {
            "symptoms": "Slope ≥0.03°C/min + duty ≥1.3× baseline + on-power ≥1.1× baseline for 3 consecutive evals.",
            "action":   "Schedule compressor inspection within 48h. Check refrigerant charge. Clean condenser coils.",
            "urgency":  "high",
        },
    }
    key = fault_code.lower().replace(" ", "_")
    return runbook.get(key, {"error": f"unknown fault_code: {fault_code}",
                              "available": list(runbook.keys())})


def create_work_order(unit_id: str, urgency: str, action: str,
                      description: str, agent_run_id: str) -> dict:
    """Insert a work order row into BigQuery."""
    valid_urgency = {"low", "medium", "high", "critical"}
    if urgency not in valid_urgency:
        urgency = "medium"

    wo_id = f"WO-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M')}-{uuid.uuid4().hex[:6].upper()}"
    row = {
        "work_order_id": wo_id,
        "unit_id":       unit_id,
        "created_at":    datetime.now(timezone.utc).isoformat(),
        "urgency":       urgency,
        "action":        action[:200],
        "description":   description[:1000],
        "status":        "open",
        "agent_run_id":  agent_run_id,
    }
    errs = bq.insert_rows_json(f"{PROJECT_ID}.{DATASET}.work_orders", [row])
    if errs:
        log.error("WO insert error: %s", errs)
        return {"error": str(errs)}
    log.info("Created work order %s for %s urgency=%s", wo_id, unit_id, urgency)
    return {"work_order_id": wo_id, "unit_id": unit_id, "urgency": urgency, "status": "open"}


def get_open_work_orders(unit_id: str | None = None) -> dict:
    """Get open work orders, optionally filtered by unit."""
    where = "WHERE status = 'open'"
    if unit_id:
        where += f" AND unit_id = '{unit_id}'"
    sql = f"""
        SELECT work_order_id, unit_id, urgency, action, created_at, status
        FROM {_table('work_orders')}
        {where}
        ORDER BY created_at DESC
        LIMIT 20
    """
    rows = _q(sql)
    return {
        "open_count": len(rows),
        "work_orders": [{k: (str(v) if isinstance(v, datetime) else v)
                          for k, v in r.items()} for r in rows],
    }


# ── Tool dispatch map ─────────────────────────────────────────────────────────
TOOLS = {
    "get_unit_status":      get_unit_status,
    "get_trend":            get_trend,
    "get_anomalies":        get_anomalies,
    "search_runbook":       search_runbook,
    "create_work_order":    create_work_order,
    "get_open_work_orders": get_open_work_orders,
}

TOOL_DECLARATIONS = [
    {
        "name": "get_unit_status",
        "description": "Get the latest telemetry and health state for a cold storage unit.",
        "parameters": {
            "type": "object",
            "properties": {"unit_id": {"type": "string", "description": "Unit ID e.g. CS-01"}},
            "required": ["unit_id"],
        },
    },
    {
        "name": "get_trend",
        "description": "Get telemetry trend statistics for a unit over the last N minutes.",
        "parameters": {
            "type": "object",
            "properties": {
                "unit_id": {"type": "string"},
                "minutes": {"type": "integer", "description": "Lookback window in minutes (default 30)"},
            },
            "required": ["unit_id"],
        },
    },
    {
        "name": "get_anomalies",
        "description": "Get recent ML anomaly detection results for a unit.",
        "parameters": {
            "type": "object",
            "properties": {
                "unit_id": {"type": "string"},
                "hours":   {"type": "integer", "description": "Lookback in hours (default 6)"},
            },
            "required": ["unit_id"],
        },
    },
    {
        "name": "search_runbook",
        "description": "Look up maintenance runbook guidance for a fault code.",
        "parameters": {
            "type": "object",
            "properties": {
                "fault_code": {
                    "type": "string",
                    "description": "Fault code e.g. compressor_degradation, door_open, pm_warning",
                }
            },
            "required": ["fault_code"],
        },
    },
    {
        "name": "create_work_order",
        "description": "Create a maintenance work order in BigQuery.",
        "parameters": {
            "type": "object",
            "properties": {
                "unit_id":      {"type": "string"},
                "urgency":      {"type": "string", "enum": ["low","medium","high","critical"]},
                "action":       {"type": "string", "description": "Short action title"},
                "description":  {"type": "string", "description": "Detailed description"},
                "agent_run_id": {"type": "string"},
            },
            "required": ["unit_id", "urgency", "action", "description", "agent_run_id"],
        },
    },
    {
        "name": "get_open_work_orders",
        "description": "List open work orders, optionally filtered by unit.",
        "parameters": {
            "type": "object",
            "properties": {
                "unit_id": {"type": "string", "description": "Filter by unit (optional)"},
            },
        },
    },
]


# ── Gemini agentic loop ────────────────────────────────────────────────────────

def _call_gemini(messages: list[dict], tool_trace: list[dict]) -> tuple[str | None, bool]:
    """
    Run one Gemini function-calling loop.
    Returns (final_text, llm_failed).
    Mutates tool_trace with each tool call made.
    """
    import google.auth
    import google.auth.transport.requests
    import requests as _requests

    try:
        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        req = google.auth.transport.requests.Request()
        creds.refresh(req)
        token = creds.token
    except Exception as e:
        log.error("ADC refresh failed: %s", e)
        return None, True

    url = (f"https://aiplatform.googleapis.com/v1/projects/{PROJECT_ID}"
           f"/locations/{LOCATION}/publishers/google/models/{GEMINI_MODEL}:generateContent")

    MAX_TURNS = 8
    for turn in range(MAX_TURNS):
        body: dict[str, Any] = {
            "contents": messages,
            "tools": [{"functionDeclarations": TOOL_DECLARATIONS}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 2048},
        }
        try:
            r = _requests.post(url, json=body,
                               headers={"Authorization": f"Bearer {token}"},
                               timeout=60)
        except Exception as e:
            log.error("Gemini HTTP error: %s", e)
            return None, True

        if r.status_code != 200:
            log.error("Gemini %d: %s", r.status_code, r.text[:200])
            return None, True

        data = r.json()
        candidate = data.get("candidates", [{}])[0]
        content   = candidate.get("content", {})
        parts     = content.get("parts", [])

        # Collect function calls
        fn_calls = [p["functionCall"] for p in parts if "functionCall" in p]
        if not fn_calls:
            # Model returned text — done
            text = "".join(p.get("text", "") for p in parts)
            return text.strip(), False

        # Append model turn
        messages.append({"role": "model", "parts": parts})

        # Execute tool calls and build function response parts
        response_parts = []
        for fn in fn_calls:
            name = fn["name"]
            args = fn.get("args", {})
            log.info("Tool call: %s(%s)", name, args)
            tool_trace.append({"tool": name, "args": args, "turn": turn})

            if name in TOOLS:
                try:
                    result = TOOLS[name](**args)
                except Exception as e:
                    result = {"error": str(e)}
            else:
                result = {"error": f"unknown tool: {name}"}

            tool_trace[-1]["result_summary"] = str(result)[:200]
            response_parts.append({
                "functionResponse": {
                    "name": name,
                    "response": {"content": result},
                }
            })

        messages.append({"role": "user", "parts": response_parts})

    log.warning("Gemini: max turns reached")
    return None, True


# ── Main cycle logic ──────────────────────────────────────────────────────────

def _run_agent_cycle(run_id: str, trigger: str) -> dict:
    started_at = datetime.now(timezone.utc)
    tool_trace: list[dict] = []
    decisions:  list[dict] = []
    llm_failed = False

    log.info("Agent cycle start run_id=%s trigger=%s", run_id, trigger)

    # Step 1: run cloud-side detection for each unit
    detection_results = {}
    for unit_id in VALID_UNITS:
        sql = f"""
            SELECT ts, unit_id, temp_avg_c, humidity_avg_pct,
                   compressor_duty, power_avg_kw, on_power_avg_kw,
                   temp_slope_c_per_min, health_state, health_score
            FROM {_table('telemetry_1min')}
            WHERE unit_id = '{unit_id}'
              AND ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {WINDOW_MIN} MINUTE)
            ORDER BY ts ASC
        """
        rows = _q(sql)
        window = TelemetryWindow(unit_id=unit_id,
                                 rows=[{k: (str(v) if isinstance(v, datetime) else v)
                                        for k, v in r.items()} for r in rows])
        detection_results[unit_id] = evaluate_unit(window)

    # Step 2: get open work orders once (to avoid duplicates)
    open_wos_data = get_open_work_orders()
    open_wos = open_wos_data.get("work_orders", [])

    # Step 3: for each unit with non-OK state, run LLM or deterministic fallback
    units_needing_attention = [
        dr for dr in detection_results.values()
        if dr.health_state != "OK" or dr.triggers
    ]

    if not units_needing_attention:
        log.info("All units OK — no action needed")
        decisions = [{"unit_id": u, "action": "no_action", "urgency": "low",
                      "health_state": "OK", "source": "detect"}
                     for u in VALID_UNITS]
    else:
        for dr in units_needing_attention:
            log.info("Unit %s state=%s triggers=%s", dr.unit_id, dr.health_state, dr.triggers)

            # Build prompt for LLM
            system_prompt = (
                "You are a predictive maintenance agent for cold storage refrigeration units. "
                "Your job: assess each unit's status, check for faults, consult the runbook, "
                "check for open work orders, and create a work order only when needed. "
                "Be concise. Use tools to gather data. End with a JSON summary:\n"
                '{"unit_id":"...", "action":"no_action|create_work_order|escalate", '
                '"urgency":"low|medium|high|critical", "description":"...", "reasoning":"..."}'
            )
            user_msg = (
                f"Evaluate unit {dr.unit_id}. "
                f"Cloud detection result: health_state={dr.health_state}, "
                f"triggers={dr.triggers}. "
                f"Detection details: {json.dumps(dr.details, default=str)}. "
                f"agent_run_id={run_id}. "
                "Check status, trend, anomalies, consult runbook if needed, "
                "check open work orders, and decide whether to create a work order."
            )
            messages = [
                {"role": "user", "parts": [{"text": system_prompt + "\n\n" + user_msg}]}
            ]

            llm_text, failed = _call_gemini(messages, tool_trace)
            llm_failed = llm_failed or failed

            if failed or not llm_text:
                log.warning("LLM failed for %s — using deterministic fallback", dr.unit_id)
                decision = make_decision(
                    unit_id=dr.unit_id,
                    health_state=dr.health_state,
                    triggers=dr.triggers,
                    details=dr.details,
                    open_work_orders=open_wos,
                )
                decisions.append(decision)
            else:
                # Parse LLM JSON summary from response
                decision = _parse_llm_decision(dr.unit_id, llm_text)
                decision["source"] = "llm"
                decisions.append(decision)

        # Units that were OK — add no_action entries
        ok_units = [u for u in VALID_UNITS
                    if u not in {dr.unit_id for dr in units_needing_attention}]
        for unit_id in ok_units:
            decisions.append({"unit_id": unit_id, "action": "no_action",
                               "urgency": "low", "health_state": "OK",
                               "source": "detect"})

    # Step 4: log agent_run to BigQuery
    completed_at = datetime.now(timezone.utc)
    run_row = {
        "run_id":          run_id,
        "started_at":      started_at.isoformat(),
        "completed_at":    completed_at.isoformat(),
        "trigger":         trigger,
        "units_evaluated": VALID_UNITS,
        "decisions":       json.dumps(decisions, default=str),
        "tool_trace":      json.dumps(tool_trace, default=str),
        "llm_failed":      llm_failed,
        "model_used":      GEMINI_MODEL if not llm_failed else "deterministic",
    }
    errs = bq.insert_rows_json(f"{PROJECT_ID}.{DATASET}.agent_runs", [run_row])
    if errs:
        log.error("agent_runs insert error: %s", errs)

    summary = {
        "run_id":          run_id,
        "started_at":      started_at.isoformat(),
        "completed_at":    completed_at.isoformat(),
        "trigger":         trigger,
        "units_evaluated": len(VALID_UNITS),
        "decisions":       decisions,
        "tool_calls":      len(tool_trace),
        "llm_failed":      llm_failed,
        "model_used":      run_row["model_used"],
    }
    log.info("Agent cycle done run_id=%s decisions=%d llm_failed=%s",
             run_id, len(decisions), llm_failed)
    return summary


def _parse_llm_decision(unit_id: str, text: str) -> dict:
    """Extract the JSON decision block from LLM text output."""
    import re
    # Try to find JSON object in the response
    match = re.search(r'\{[^{}]*"action"[^{}]*\}', text, re.DOTALL)
    if match:
        try:
            d = json.loads(match.group())
            d.setdefault("unit_id", unit_id)
            return d
        except json.JSONDecodeError:
            pass
    # Fallback: return text as description
    return {
        "unit_id": unit_id,
        "action": "no_action",
        "urgency": "low",
        "description": text[:500],
        "reasoning": "Could not parse structured decision from LLM output.",
    }


# ── FastAPI endpoints ─────────────────────────────────────────────────────────

@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": "maintenance-agent", "version": "1.0.0",
            "model": GEMINI_MODEL, "location": LOCATION}


@app.post("/run-cycle")
async def run_cycle(background_tasks: BackgroundTasks, dry_run: bool = False):
    """Trigger one maintenance cycle. dry_run=true skips BQ writes."""
    run_id  = f"run-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
    trigger = "dry_run" if dry_run else "scheduler"

    if dry_run:
        # Run synchronously and return result
        summary = _run_agent_cycle(run_id, trigger)
        return JSONResponse(content=summary)

    # Real run — execute in background, return immediately (Cloud Scheduler expects 2xx fast)
    background_tasks.add_task(_run_agent_cycle, run_id, trigger)
    return JSONResponse(content={"status": "accepted", "run_id": run_id}, status_code=202)


@app.get("/last-run")
def last_run():
    sql = f"""
        SELECT run_id, started_at, completed_at, trigger,
               llm_failed, model_used
        FROM {_table('agent_runs')}
        ORDER BY started_at DESC
        LIMIT 1
    """
    rows = _q(sql)
    if not rows:
        return {"error": "no runs yet"}
    r = rows[0]
    return {k: (str(v) if isinstance(v, datetime) else v) for k, v in r.items()}


@app.post("/admin/retrain")
def retrain():
    """Placeholder: trigger BQML model retrain via BigQuery scheduled query."""
    log.info("Retrain triggered (placeholder)")
    return {"status": "accepted", "message": "BQML retrain scheduled (placeholder)"}
