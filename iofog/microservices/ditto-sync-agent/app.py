#!/usr/bin/env python3
"""
Ditto Sync Agent — Smart Cold Storage Digital Twin
===================================================
Subscribes to sensor readings and anomaly scores via ioFog message bus.
Patches the corresponding Eclipse Ditto digital twin on GCP via HTTPS.

Offline resilience: SQLite buffer stores up to BUFFER_SIZE events.
On reconnect, buffered events are replayed with exponential backoff.

Two types of Ditto PATCHes:
  1. Sensor reading  → updates temperature, humidity, compressor, energy, connectivity
  2. Anomaly score   → updates maintenance and anomaly features
"""

import os
import time
import json
import sqlite3
import logging
import threading
import requests
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Optional
from queue import Queue, Empty

# ─── Configuration ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s"
)
log = logging.getLogger("ditto-sync")

UNIT_IDS        = os.environ.get("UNIT_IDS", "CS-01,CS-02").split(",")
WAREHOUSE_ID    = os.environ.get("WAREHOUSE_ID", "alpha")
DITTO_URL       = os.environ.get("DITTO_URL", "http://ditto-gateway:8080")
DITTO_AUTH_HDR  = os.environ.get("DITTO_AUTH_HEADER", "x-ditto-pre-authenticated")
DITTO_AUTH_VAL  = os.environ.get("DITTO_AUTH_VALUE", "nginx:nodered")
BUFFER_SIZE     = int(os.environ.get("BUFFER_SIZE", "2000"))
RETRY_BASE      = float(os.environ.get("RETRY_BACKOFF_BASE", "1.0"))
IOFOG_BUS_URL   = os.environ.get("IOFOG_BUS_URL", "http://localhost:54321")
POLL_INTERVAL   = int(os.environ.get("POLL_INTERVAL_SECONDS", "3"))
DB_PATH         = os.environ.get("DB_PATH", "/tmp/ditto_sync_buffer.db")

# ─── SQLite Buffer ────────────────────────────────────────────────────────────
def init_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sync_buffer (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            unit_id     TEXT NOT NULL,
            event_type  TEXT NOT NULL,
            payload     TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            attempts    INTEGER DEFAULT 0
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_unit ON sync_buffer(unit_id)")
    conn.commit()
    # Trim to buffer size
    conn.execute(f"""
        DELETE FROM sync_buffer WHERE id NOT IN (
            SELECT id FROM sync_buffer ORDER BY id DESC LIMIT {BUFFER_SIZE}
        )
    """)
    conn.commit()
    count = conn.execute("SELECT COUNT(*) FROM sync_buffer").fetchone()[0]
    log.info(f"SQLite buffer initialized: {count} pending events")
    return conn


def buffer_event(conn: sqlite3.Connection, unit_id: str, event_type: str, payload: dict):
    conn.execute(
        "INSERT INTO sync_buffer (unit_id, event_type, payload, created_at) VALUES (?,?,?,?)",
        (unit_id, event_type, json.dumps(payload), datetime.now(timezone.utc).isoformat())
    )
    conn.commit()


def get_pending_events(conn: sqlite3.Connection, limit: int = 50):
    return conn.execute(
        "SELECT id, unit_id, event_type, payload, attempts FROM sync_buffer ORDER BY id ASC LIMIT ?",
        (limit,)
    ).fetchall()


def delete_event(conn: sqlite3.Connection, event_id: int):
    conn.execute("DELETE FROM sync_buffer WHERE id=?", (event_id,))
    conn.commit()


def increment_attempts(conn: sqlite3.Connection, event_id: int):
    conn.execute("UPDATE sync_buffer SET attempts=attempts+1 WHERE id=?", (event_id,))
    conn.commit()


# ─── Ditto Payloads ───────────────────────────────────────────────────────────
def build_sensor_patch(data: dict) -> dict:
    """Build PATCH payload for sensor reading → Ditto Thing features"""
    ts = data.get("timestamp", datetime.now(timezone.utc).isoformat())

    temp_val = data.get("temperature", 0)
    temp_status = "critical" if temp_val >= 10 else "warning" if temp_val >= 8 else "normal"

    hum_val = data.get("humidity", 65)
    hum_status = "warning" if (hum_val > 80 or hum_val < 50) else "normal"

    energy_val = data.get("energyConsumption", 0)
    energy_eff = "critical" if energy_val >= 4 else "inefficient" if energy_val >= 3 else "normal"

    return {
        "features": {
            "temperature": {
                "properties": {
                    "value": temp_val,
                    "status": temp_status,
                    "lastUpdated": ts
                }
            },
            "humidity": {
                "properties": {
                    "value": hum_val,
                    "status": hum_status,
                    "lastUpdated": ts
                }
            },
            "compressor": {
                "properties": {
                    "status": data.get("compressorStatus", "OFF"),
                    "lastUpdated": ts
                }
            },
            "energy": {
                "properties": {
                    "consumption": energy_val,
                    "efficiency": energy_eff,
                    "lastUpdated": ts
                }
            },
            "connectivity": {
                "properties": {
                    "connected": True,
                    "lastSeen": ts,
                    "warehouseId": WAREHOUSE_ID
                }
            }
        }
    }


def build_anomaly_patch(data: dict) -> dict:
    """Build PATCH payload for anomaly score → Ditto Thing maintenance + anomaly features"""
    now = datetime.now(timezone.utc).isoformat()
    score = data.get("score", 0.0)
    risk = data.get("riskLevel", "normal")

    health = "critical" if risk == "critical" else \
             "attention" if risk in ("high", "warning") else "healthy"

    health_score = max(0, int(100 - score * 100))

    return {
        "features": {
            "maintenance": {
                "properties": {
                    "score": int(score * 100),
                    "temperatureStability": int((1 - data.get("zscore_temp", 0)) * 100),
                    "energyEfficiency": int((1 - data.get("zscore_energy", 0)) * 100),
                    "compressorHealth": int((1 - data.get("compressor_score", 0)) * 100),
                    "recommendation": data.get("explanation", "No details"),
                    "priority": risk,
                    "lastCalculated": now
                }
            },
            "anomaly": {
                "properties": {
                    "edgeScore": score,
                    "cloudScore": None,
                    "riskLevel": risk,
                    "dominantSignal": data.get("dominantSignal", "unknown"),
                    "explanation": data.get("explanation", ""),
                    "trendDirection": data.get("trend_direction", "stable"),
                    "lastEvaluated": now
                }
            },
            "status": {
                "properties": {
                    "health": health,
                    "healthScore": health_score
                }
            }
        }
    }


# ─── Ditto HTTP Client ────────────────────────────────────────────────────────
def patch_ditto(unit_id: str, payload: dict) -> bool:
    """Send PATCH to GCP Eclipse Ditto. Returns True on success."""
    thing_id = f"org.eclipse.ditto:{unit_id}"
    url = f"{DITTO_URL}/api/2/things/{thing_id}"
    headers = {
        "Content-Type": "application/merge-patch+json",
        DITTO_AUTH_HDR: DITTO_AUTH_VAL
    }
    try:
        resp = requests.patch(url, json=payload, headers=headers, timeout=10)
        if resp.status_code in (200, 204):
            return True
        elif resp.status_code == 404:
            log.warning(f"Thing {thing_id} not found in Ditto — creating it")
            return create_ditto_thing(unit_id)
        else:
            log.warning(f"Ditto PATCH {thing_id}: HTTP {resp.status_code} — {resp.text[:100]}")
            return False
    except requests.exceptions.ConnectionError:
        log.debug(f"Ditto unreachable at {DITTO_URL}")
        return False
    except Exception as e:
        log.warning(f"Ditto PATCH error: {e}")
        return False


def create_ditto_thing(unit_id: str) -> bool:
    """Create a new Thing in Ditto if it doesn't exist"""
    thing_id = f"org.eclipse.ditto:{unit_id}"
    url = f"{DITTO_URL}/api/2/things/{thing_id}"
    headers = {
        "Content-Type": "application/json",
        DITTO_AUTH_HDR: DITTO_AUTH_VAL
    }
    payload = {
        "policyId": "org.eclipse.ditto:cold-storage-policy",
        "definition": "org.eclipse.ditto:ColdStorageUnit:1.0.0",
        "attributes": {
            "unitId": unit_id,
            "warehouseId": WAREHOUSE_ID,
            "createdBy": "ditto-sync-agent"
        },
        "features": {
            "temperature":   {"properties": {"value": 4.0, "status": "normal"}},
            "humidity":      {"properties": {"value": 65.0, "status": "normal"}},
            "compressor":    {"properties": {"status": "OFF", "health": "healthy"}},
            "energy":        {"properties": {"consumption": 0.0, "efficiency": "normal"}},
            "connectivity":  {"properties": {"connected": True, "warehouseId": WAREHOUSE_ID}},
            "maintenance":   {"properties": {"score": 0, "priority": "low", "recommendation": "Normal"}},
            "anomaly":       {"properties": {"edgeScore": 0.0, "riskLevel": "normal"}},
            "status":        {"properties": {"health": "healthy", "healthScore": 100}}
        }
    }
    try:
        resp = requests.put(url, json=payload, headers=headers, timeout=10)
        return resp.status_code in (200, 201, 204)
    except Exception as e:
        log.warning(f"Could not create Thing {thing_id}: {e}")
        return False


# ─── ioFog Message Bus Polling ────────────────────────────────────────────────
def poll_iofog_bus(conn: sqlite3.Connection):
    """Poll ioFog message bus for incoming sensor readings and anomaly scores"""
    try:
        resp = requests.get(
            f"{IOFOG_BUS_URL}/v2/messages/next",
            timeout=5
        )
        if resp.status_code != 200:
            return

        messages = resp.json().get("messages", [])
        for msg in messages:
            content_raw = msg.get("contentdata", "{}")
            try:
                content = json.loads(content_raw)
                msg_type = content.get("type", "sensor_reading")
                data = content.get("data", content)
                unit_id = data.get("unitId", "")

                if not unit_id or unit_id.strip() not in [u.strip() for u in UNIT_IDS]:
                    continue

                buffer_event(conn, unit_id.strip(), msg_type, data)

            except json.JSONDecodeError:
                pass

    except Exception as e:
        log.debug(f"ioFog bus poll error (non-critical): {e}")


# ─── Sync Worker ──────────────────────────────────────────────────────────────
def sync_worker(conn: sqlite3.Connection):
    """
    Worker thread: drains the SQLite buffer by sending events to Ditto.
    Uses exponential backoff on failure.
    """
    backoff = RETRY_BASE

    while True:
        events = get_pending_events(conn, limit=20)

        if not events:
            time.sleep(2)
            backoff = RETRY_BASE
            continue

        all_succeeded = True

        for event_id, unit_id, event_type, payload_json, attempts in events:
            try:
                payload_data = json.loads(payload_json)

                if event_type == "sensor_reading":
                    ditto_payload = build_sensor_patch(payload_data)
                elif event_type == "anomaly_score":
                    ditto_payload = build_anomaly_patch(payload_data)
                else:
                    # Unknown type — discard
                    delete_event(conn, event_id)
                    continue

                success = patch_ditto(unit_id, ditto_payload)

                if success:
                    delete_event(conn, event_id)
                    log.debug(f"Synced {event_type} for {unit_id}")
                    backoff = RETRY_BASE
                else:
                    increment_attempts(conn, event_id)
                    all_succeeded = False

                    # Drop events that have failed too many times
                    if attempts >= 10:
                        log.warning(f"Dropping event {event_id} for {unit_id} after 10 failed attempts")
                        delete_event(conn, event_id)

            except Exception as e:
                log.error(f"Error processing event {event_id}: {e}")
                increment_attempts(conn, event_id)
                all_succeeded = False

        if not all_succeeded:
            # Exponential backoff: 1s, 2s, 4s, 8s, 16s, 32s, cap at 60s
            wait = min(backoff, 60)
            log.info(f"Ditto unreachable — retrying in {wait:.0f}s (backoff={backoff:.0f}s)")
            time.sleep(wait)
            backoff = min(backoff * 2, 60)
        else:
            time.sleep(0.5)


# ─── Direct MQTT-to-Ditto Fast Path ──────────────────────────────────────────
def direct_sync_from_nodered_webhook(conn: sqlite3.Connection):
    """
    Flask micro-server to receive direct pushes from Node-RED.
    Node-RED POSTs sensor readings here instead of patching Ditto itself.
    This is faster than the ioFog bus poll cycle.
    """
    from flask import Flask, request, jsonify
    app = Flask(__name__)

    @app.route("/sync/sensor", methods=["POST"])
    def sync_sensor():
        data = request.get_json(silent=True) or {}
        unit_id = data.get("unitId", "")
        if unit_id:
            buffer_event(conn, unit_id, "sensor_reading", data)
        return jsonify({"status": "buffered"}), 202

    @app.route("/sync/anomaly", methods=["POST"])
    def sync_anomaly():
        data = request.get_json(silent=True) or {}
        unit_id = data.get("unitId", "")
        if unit_id:
            buffer_event(conn, unit_id, "anomaly_score", data)
        return jsonify({"status": "buffered"}), 202

    @app.route("/health", methods=["GET"])
    def health():
        pending = conn.execute("SELECT COUNT(*) FROM sync_buffer").fetchone()[0]
        return jsonify({"status": "ok", "pending_events": pending}), 200

    log.info("Ditto Sync Agent HTTP server on port 8082")
    app.run(host="0.0.0.0", port=8082, debug=False)


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    log.info("=" * 60)
    log.info("  Ditto Sync Agent — Smart Cold Storage")
    log.info("=" * 60)
    log.info(f"  Units     : {UNIT_IDS}")
    log.info(f"  Warehouse : {WAREHOUSE_ID}")
    log.info(f"  Ditto URL : {DITTO_URL}")
    log.info(f"  Buffer    : {BUFFER_SIZE} events max (SQLite: {DB_PATH})")
    log.info("=" * 60)

    # Initialize SQLite buffer
    conn = init_db()

    # Start sync worker thread
    worker = threading.Thread(target=sync_worker, args=(conn,), daemon=True)
    worker.start()
    log.info("Sync worker thread started")

    # Start HTTP webhook server in background thread
    webhook_thread = threading.Thread(
        target=direct_sync_from_nodered_webhook, args=(conn,), daemon=True
    )
    webhook_thread.start()

    # Main loop: poll ioFog message bus
    log.info(f"Polling ioFog bus every {POLL_INTERVAL}s...")
    while True:
        poll_iofog_bus(conn)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
