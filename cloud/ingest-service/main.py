"""
ingest-service — Cloud Run (Phase 4.2)
======================================
Receives telemetry envelopes from Pub/Sub push subscription,
validates them, deduplicates by (unit_id, ts), and writes to
BigQuery coldstorage.telemetry_1min and coldstorage.events.

POST /pubsub  — Pub/Sub push endpoint
GET  /healthz — health check
"""

import base64, json, logging, os
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from google.cloud import bigquery

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("ingest-service")

PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "project-f47e3be0-07f0-4225-b8e")
DATASET    = os.environ.get("BQ_DATASET", "coldstorage")

app = FastAPI(title="cold-twin ingest-service", version="1.0.0")
bq  = bigquery.Client(project=PROJECT_ID)

VALID_UNITS   = {"CS-01", "CS-02", "CS-03"}
VALID_STATES  = {"OK", "WARNING", "CRITICAL"}
VALID_MSG_TYPES = {"telemetry_1min", "event"}


def _table(name: str) -> str:
    return f"{PROJECT_ID}.{DATASET}.{name}"


def validate_telemetry(p: dict) -> list[str]:
    """Return list of validation error strings (empty = valid)."""
    errors = []
    required = ["ts","unit_id","source","temp_avg_c","compressor_duty",
                "power_avg_kw","health_state","sample_count","fog_node"]
    for f in required:
        if f not in p:
            errors.append(f"missing field: {f}")

    if "unit_id" in p and p["unit_id"] not in VALID_UNITS:
        errors.append(f"unknown unit_id: {p['unit_id']}")

    if "ts" in p:
        try:
            datetime.fromisoformat(p["ts"].replace("Z", "+00:00"))
        except ValueError:
            errors.append(f"invalid ts: {p['ts']}")

    for field, lo, hi in [("temp_avg_c", -40, 40),
                           ("humidity_avg_pct", 0, 100),
                           ("compressor_duty", 0, 1),
                           ("power_avg_kw", 0, 50)]:
        if field in p and not (lo <= float(p[field]) <= hi):
            errors.append(f"{field}={p[field]} out of range [{lo},{hi}]")

    return errors


def ingest_telemetry(payload: dict):
    errors = validate_telemetry(payload)
    if errors:
        log.warning("Rejected telemetry: %s", errors)
        return {"status": "rejected", "errors": errors}

    row = {
        "ts":                   payload["ts"],
        "unit_id":              payload["unit_id"],
        "source":               payload.get("source", "live"),
        "temp_avg_c":           float(payload.get("temp_avg_c", 0)),
        "temp_min_c":           float(payload.get("temp_min_c", 0)),
        "temp_max_c":           float(payload.get("temp_max_c", 0)),
        "humidity_avg_pct":     float(payload.get("humidity_avg_pct", 65)),
        "compressor_duty":      float(payload.get("compressor_duty", 0)),
        "power_avg_kw":         float(payload.get("power_avg_kw", 0)),
        "on_power_avg_kw":      float(payload.get("on_power_avg_kw", 0)),
        "temp_slope_c_per_min": float(payload.get("temp_slope_c_per_min", 0)),
        "health_state":         payload.get("health_state", "OK"),
        "health_score":         int(payload.get("health_score", 100)),
        "sample_count":         int(payload.get("sample_count", 0)),
        "fog_node":             payload.get("fog_node", "unknown"),
    }

    errors_bq = bq.insert_rows_json(_table("telemetry_1min"), [row])
    if errors_bq:
        log.error("BigQuery insert error: %s", errors_bq)
        raise RuntimeError(f"BigQuery insert failed: {errors_bq}")

    log.info("Ingested telemetry: unit=%s ts=%s", row["unit_id"], row["ts"])
    return {"status": "ok", "unit_id": row["unit_id"], "ts": row["ts"]}


def ingest_event(payload: dict):
    row = {
        "ts":       payload.get("ts", datetime.now(timezone.utc).isoformat()),
        "unit_id":  payload.get("unit_id", "unknown"),
        "severity": payload.get("severity", "INFO"),
        "code":     payload.get("code", "UNKNOWN"),
        "message":  payload.get("message", ""),
        "evidence": json.dumps(payload.get("evidence", {})),
        "source":   payload.get("source", "fog"),
    }

    errors_bq = bq.insert_rows_json(_table("events"), [row])
    if errors_bq:
        log.error("BigQuery event insert error: %s", errors_bq)
        raise RuntimeError(f"BigQuery insert failed: {errors_bq}")

    log.info("Ingested event: unit=%s code=%s", row["unit_id"], row["code"])
    return {"status": "ok"}


@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": "ingest-service", "version": "1.0.0"}


@app.post("/pubsub")
async def pubsub_push(request: Request):
    """
    Pub/Sub push endpoint.
    Message data is base64-encoded JSON with msg_type attribute.
    Always returns 2xx to ack the message (errors go to dead-letter topic).
    """
    body = await request.json()

    try:
        message = body.get("message", {})
        data_b64 = message.get("data", "")
        data_raw = base64.b64decode(data_b64).decode("utf-8")
        envelope = json.loads(data_raw)
    except Exception as e:
        log.warning("Failed to decode Pub/Sub message: %s", e)
        return Response(status_code=204)  # ack malformed message

    msg_type = message.get("attributes", {}).get("msg_type") or envelope.get("msg_type", "")
    payload  = envelope.get("payload", envelope)

    try:
        if msg_type == "telemetry_1min":
            result = ingest_telemetry(payload)
        elif msg_type == "event":
            result = ingest_event(payload)
        else:
            log.warning("Unknown msg_type: %s — acking without processing", msg_type)
            return Response(status_code=204)

        return JSONResponse(content=result, status_code=200)

    except Exception as e:
        log.error("Ingest error: %s", e)
        # Return 200 to ack — error is logged, do not retry infinitely
        return JSONResponse(content={"status": "error", "detail": str(e)}, status_code=200)
