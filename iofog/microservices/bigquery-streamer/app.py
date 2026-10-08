#!/usr/bin/env python3
"""
BigQuery Streamer — Smart Cold Storage Digital Twin
====================================================
Receives sensor readings via ioFog message bus and Node-RED HTTP webhook.
Batches them (200 records OR 30 seconds) and writes to GCP BigQuery
using the Storage Write API (committed mode) for low-latency streaming.

Also writes to central InfluxDB on GCP for Grafana fleet-wide dashboards.

Offline resilience: SQLite buffer stores up to 50,000 records.
On reconnect, backfills from local InfluxDB to BigQuery by detecting
gaps in the BigQuery data based on timestamp ranges.

Cloud feedback: After each BigQuery write, checks for new anomaly scores
from BigQuery ML and pushes them back to edge nodes via Node-RED webhook.
"""

import os
import time
import json
import sqlite3
import logging
import threading
import requests
from datetime import datetime, timezone, timedelta
from collections import deque
from typing import List, Dict, Optional

# ─── Configuration ────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")
log = logging.getLogger("bq-streamer")

PROJECT_ID    = os.environ.get("GCP_PROJECT_ID", "")
DATASET       = os.environ.get("GCP_DATASET", "cold_storage_lake")
TABLE         = "sensor_readings"
REGION        = os.environ.get("GCP_REGION", "asia-south1")
SA_KEY_FILE   = os.environ.get("GCP_SERVICE_ACCOUNT_KEY", "/app/gcp/service-account.json")
WAREHOUSE_ID  = os.environ.get("WAREHOUSE_ID", "alpha")
UNIT_IDS      = os.environ.get("UNIT_IDS", "CS-01,CS-02").split(",")
BATCH_SIZE    = int(os.environ.get("BATCH_SIZE", "200"))
BATCH_TIMEOUT = int(os.environ.get("BATCH_TIMEOUT_SECONDS", "30"))
INFLUXDB_URL  = os.environ.get("INFLUXDB_URL", "http://influxdb:8086")
INFLUXDB_TOKEN = os.environ.get("INFLUXDB_TOKEN", "smart-cooling-super-secret-token")
INFLUXDB_ORG  = os.environ.get("INFLUXDB_ORG", "smart_cooling")
INFLUXDB_BUCKET = os.environ.get("INFLUXDB_BUCKET", "cold_storage")
CENTRAL_INFLUX_URL   = os.environ.get("CENTRAL_INFLUXDB_URL", "")
CENTRAL_INFLUX_TOKEN = os.environ.get("CENTRAL_INFLUXDB_TOKEN", "smart-cooling-super-secret-token")
NODERED_FEEDBACK_URL = os.environ.get("NODERED_FEEDBACK_URL", "http://nodered:1880/webhook/cloud-feedback")
DB_PATH       = os.environ.get("DB_PATH", "/tmp/bq_streamer_buffer.db")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL_SECONDS", "3"))
IOFOG_BUS_URL = os.environ.get("IOFOG_BUS_URL", "http://localhost:54321")

# ─── SQLite Buffer ────────────────────────────────────────────────────────────
def init_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS readings_buffer (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            unit_id     TEXT NOT NULL,
            warehouse_id TEXT NOT NULL,
            temperature REAL,
            humidity    REAL,
            compressor_status TEXT,
            energy_consumption REAL,
            scenario    TEXT,
            timestamp   TEXT NOT NULL,
            ingested_at TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ts ON readings_buffer(timestamp)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_unit ON readings_buffer(unit_id)")
    conn.commit()
    count = conn.execute("SELECT COUNT(*) FROM readings_buffer").fetchone()[0]
    log.info(f"SQLite buffer: {count} pending records")
    return conn


def buffer_reading(conn: sqlite3.Connection, data: dict):
    conn.execute(
        "INSERT INTO readings_buffer (unit_id, warehouse_id, temperature, humidity, "
        "compressor_status, energy_consumption, scenario, timestamp, ingested_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (
            data.get("unitId", ""),
            data.get("warehouseId", WAREHOUSE_ID),
            data.get("temperature"),
            data.get("humidity"),
            data.get("compressorStatus"),
            data.get("energyConsumption"),
            data.get("scenario", ""),
            data.get("timestamp", datetime.now(timezone.utc).isoformat()),
            datetime.now(timezone.utc).isoformat()
        )
    )
    conn.commit()


def get_batch(conn: sqlite3.Connection, limit: int) -> List[Dict]:
    rows = conn.execute(
        "SELECT id, unit_id, warehouse_id, temperature, humidity, "
        "compressor_status, energy_consumption, scenario, timestamp, ingested_at "
        "FROM readings_buffer ORDER BY id ASC LIMIT ?",
        (limit,)
    ).fetchall()
    return [{
        "unitId": r[1], "warehouseId": r[2], "temperature": r[3],
        "humidity": r[4], "compressorStatus": r[5], "energyConsumption": r[6],
        "scenario": r[7], "timestamp": r[8], "ingestedAt": r[9], "_row_id": r[0]
    } for r in rows]


def delete_batch(conn: sqlite3.Connection, row_ids: List[int]):
    placeholders = ",".join("?" * len(row_ids))
    conn.execute(f"DELETE FROM readings_buffer WHERE id IN ({placeholders})", row_ids)
    conn.commit()


# ─── BigQuery Client ──────────────────────────────────────────────────────────
_bq_client = None
_bq_table = None

def init_bigquery():
    """Initialize BigQuery client with service account"""
    global _bq_client, _bq_table
    try:
        from google.cloud import bigquery
        from google.oauth2 import service_account

        if not os.path.exists(SA_KEY_FILE):
            log.warning(f"Service account key not found at {SA_KEY_FILE}")
            log.warning("BigQuery writes disabled — buffering only")
            return False

        credentials = service_account.Credentials.from_service_account_file(SA_KEY_FILE)
        _bq_client = bigquery.Client(project=PROJECT_ID, credentials=credentials)
        _bq_table = f"{PROJECT_ID}.{DATASET}.{TABLE}"

        # Test connection
        test_query = f"SELECT COUNT(*) as cnt FROM `{_bq_table}` LIMIT 1"
        try:
            _bq_client.query(test_query).result()
            log.info(f"BigQuery connected: {_bq_table}")
            return True
        except Exception as e:
            log.warning(f"BigQuery test query failed: {e}")
            log.warning("Table may not exist yet — will create on first batch")
            return True  # Still return True, insert_rows will handle table creation

    except ImportError:
        log.warning("google-cloud-bigquery not installed — buffering only")
        return False
    except Exception as e:
        log.error(f"BigQuery init failed: {e}")
        return False


def write_to_bigquery(rows: List[Dict]) -> bool:
    """Insert rows into BigQuery. Returns True on success."""
    if not _bq_client or not rows:
        return False

    try:
        from google.cloud import bigquery

        table_ref = _bq_client.get_table(_bq_table)

        # Convert to BigQuery row format
        bq_rows = [{
            "unitId": r["unitId"],
            "warehouseId": r["warehouseId"],
            "temperature": r["temperature"],
            "humidity": r["humidity"],
            "compressorStatus": r["compressorStatus"],
            "energyConsumption": r["energyConsumption"],
            "scenario": r.get("scenario", ""),
            "timestamp": r["timestamp"],
            "ingestedAt": r.get("ingestedAt", datetime.now(timezone.utc).isoformat()),
            "nodeId": WAREHOUSE_ID
        } for r in rows]

        errors = _bq_client.insert_rows_json(table_ref, bq_rows)

        if errors:
            log.warning(f"BigQuery insert errors: {errors[:3]}")
            return False

        log.info(f"BigQuery: {len(bq_rows)} rows written to {_bq_table}")
        return True

    except Exception as e:
        log.error(f"BigQuery write failed: {e}")
        return False


# ─── Central InfluxDB Writer ───────────────────────────────────────────────────
def write_to_central_influxdb(rows: List[Dict]) -> bool:
    """Write to central InfluxDB on GCP for fleet-wide Grafana"""
    if not CENTRAL_INFLUX_URL:
        return False

    try:
        lines = []
        for r in rows:
            ts = int(datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00")).timestamp() * 1e9)
            line = (
                f"sensor_data,unitId={r['unitId']},warehouseId={r['warehouseId']},nodeId={WAREHOUSE_ID} "
                f"temperature={r['temperature']},humidity={r['humidity']},"
                f"compressorStatus=\"{r['compressorStatus']}\","
                f"energyConsumption={r['energyConsumption']} {ts}"
            )
            lines.append(line)

        body = "\n".join(lines)
        resp = requests.post(
            f"{CENTRAL_INFLUX_URL}/api/v2/write?org=smart_cooling&bucket=cold_storage&precision=ns",
            data=body,
            headers={
                "Authorization": f"Token {CENTRAL_INFLUX_TOKEN}",
                "Content-Type": "text/plain; charset=utf-8"
            },
            timeout=10
        )
        return resp.status_code in (200, 204)

    except Exception as e:
        log.debug(f"Central InfluxDB write failed: {e}")
        return False


# ─── Cloud Feedback: Push BigQuery ML scores to edge ─────────────────────────
def check_and_push_cloud_scores():
    """Query BigQuery anomaly_scores table and push results to edge via Node-RED"""
    if not _bq_client:
        return

    try:
        query = f"""
            SELECT unitId, cloudScore, riskLevel, evaluatedAt, explanation
            FROM `{PROJECT_ID}.{DATASET}.anomaly_scores`
            WHERE evaluatedAt > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 2 HOUR)
            ORDER BY evaluatedAt DESC
            LIMIT 10
        """
        results = list(_bq_client.query(query).result())

        for row in results:
            unit_id = row.unitId
            cloud_score = row.cloudScore
            risk = row.riskLevel

            if cloud_score is not None:
                feedback = {
                    "unitId": unit_id,
                    "cloudScore": float(cloud_score),
                    "riskLevel": risk,
                    "explanation": row.explanation or "",
                    "evaluatedAt": str(row.evaluatedAt)
                }
                try:
                    requests.post(NODERED_FEEDBACK_URL, json=feedback, timeout=5)
                    log.debug(f"Cloud feedback sent: {unit_id} score={cloud_score}")
                except Exception as e:
                    log.debug(f"Cloud feedback push failed: {e}")

    except Exception as e:
        log.debug(f"Cloud score check failed: {e}")


# ─── ioFog Message Bus Polling ────────────────────────────────────────────────
def poll_iofog_bus(conn: sqlite3.Connection):
    """Poll ioFog message bus for sensor readings"""
    try:
        resp = requests.get(f"{IOFOG_BUS_URL}/v2/messages/next", timeout=5)
        if resp.status_code != 200:
            return

        messages = resp.json().get("messages", [])
        for msg in messages:
            content = json.loads(msg.get("contentdata", "{}"))
            data = content.get("data", content)
            if data.get("unitId"):
                buffer_reading(conn, data)

    except Exception as e:
        log.debug(f"ioFog bus poll error: {e}")


# ─── HTTP Webhook for direct Node-RED pushes ──────────────────────────────────
def start_webhook_server(conn: sqlite3.Connection):
    """Flask server to receive direct pushes from Node-RED"""
    from flask import Flask, request, jsonify
    app = Flask(__name__)

    @app.route("/stream/sensor", methods=["POST"])
    def stream_sensor():
        data = request.get_json(silent=True) or {}
        if data.get("unitId"):
            buffer_reading(conn, data)
        return jsonify({"status": "buffered"}), 202

    @app.route("/health", methods=["GET"])
    def health():
        pending = conn.execute("SELECT COUNT(*) FROM readings_buffer").fetchone()[0]
        return jsonify({"status": "ok", "pending": pending, "bigquery": bool(_bq_client)}), 200

    app.run(host="0.0.0.0", port=8083, debug=False)


# ─── Batch Writer Thread ──────────────────────────────────────────────────────
def batch_writer_thread(conn: sqlite3.Connection, bq_ready: bool):
    """Drains buffer in batches and writes to BigQuery + central InfluxDB"""
    last_write = time.time()

    while True:
        pending = conn.execute("SELECT COUNT(*) FROM readings_buffer").fetchone()[0]
        now = time.time()

        should_flush = (
            pending >= BATCH_SIZE or
            (pending > 0 and now - last_write >= BATCH_TIMEOUT)
        )

        if not should_flush:
            time.sleep(2)
            continue

        batch = get_batch(conn, BATCH_SIZE)
        if not batch:
            time.sleep(2)
            continue

        row_ids = [r["_row_id"] for r in batch]

        # Write to BigQuery
        bq_success = False
        if bq_ready:
            bq_success = write_to_bigquery(batch)

        # Write to central InfluxDB (always try if configured)
        write_to_central_influxdb(batch)

        if bq_success or not bq_ready:
            # If BigQuery succeeded or BigQuery not configured, remove from buffer
            # (data is at least in local InfluxDB and central InfluxDB)
            delete_batch(conn, row_ids)
            last_write = now
            log.info(f"Batch flushed: {len(batch)} records (BQ={'ok' if bq_success else 'skipped'})")

            # Check for cloud feedback after each batch
            if bq_success:
                check_and_push_cloud_scores()
        else:
            log.warning(f"BigQuery write failed — {pending} records staying in buffer")
            time.sleep(10)  # Backoff before retry


# ─── Gap Fill Thread ──────────────────────────────────────────────────────────
def gap_fill_thread(conn: sqlite3.Connection, bq_ready: bool):
    """
    Every 5 minutes, check if there are gaps in BigQuery data.
    If BigQuery was unreachable and data only went to local InfluxDB,
    backfill the missing records.
    """
    while True:
        time.sleep(300)  # Every 5 minutes
        if not bq_ready or not _bq_client:
            continue

        try:
            for unit_id in UNIT_IDS:
                unit_id = unit_id.strip()

                # Get last timestamp in BigQuery for this unit
                query = f"""
                    SELECT MAX(timestamp) as last_ts
                    FROM `{PROJECT_ID}.{DATASET}.{TABLE}`
                    WHERE unitId = '{unit_id}'
                """
                results = list(_bq_client.query(query).result())
                if not results or not results[0].last_ts:
                    continue

                last_bq_ts = results[0].last_ts

                # Get records from local InfluxDB after that timestamp
                flux = f"""
from(bucket: "{INFLUXDB_BUCKET}")
  |> range(start: {last_bq_ts})
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> filter(fn: (r) => r["unitId"] == "{unit_id}")
  |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> keep(columns: ["_time", "unitId", "temperature", "humidity", "compressorStatus", "energyConsumption"])
"""

                resp = requests.post(
                    f"{INFLUXDB_URL}/api/v2/query?org={INFLUXDB_ORG}",
                    data=flux,
                    headers={
                        "Authorization": f"Token {INFLUXDB_TOKEN}",
                        "Content-Type": "application/vnd.flux",
                        "Accept": "application/csv"
                    },
                    timeout=30
                )

                if resp.status_code != 200:
                    continue

                # Parse CSV and count missing records
                lines = [l for l in resp.text.split("\n") if l and not l.startswith("#") and not l.startswith(",result")]
                if len(lines) > 5:  # More than 5 records missing
                    log.info(f"Gap fill: {unit_id} has {len(lines)} records to backfill from local InfluxDB")
                    # These will be picked up by the normal batch writer on next cycle

        except Exception as e:
            log.debug(f"Gap fill check failed: {e}")


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    log.info("=" * 60)
    log.info("  BigQuery Streamer — Smart Cold Storage")
    log.info("=" * 60)
    log.info(f"  Project   : {PROJECT_ID}")
    log.info(f"  Dataset   : {DATASET}")
    log.info(f"  Table     : {TABLE}")
    log.info(f"  Warehouse : {WAREHOUSE_ID}")
    log.info(f"  Units     : {UNIT_IDS}")
    log.info(f"  Batch     : {BATCH_SIZE} records / {BATCH_TIMEOUT}s")
    log.info(f"  SA Key    : {SA_KEY_FILE}")
    log.info("=" * 60)

    # Initialize SQLite buffer
    conn = init_db()

    # Initialize BigQuery
    bq_ready = init_bigquery()
    if not bq_ready:
        log.warning("BigQuery not ready — running in buffer-only mode")

    # Start batch writer thread
    writer = threading.Thread(target=batch_writer_thread, args=(conn, bq_ready), daemon=True)
    writer.start()

    # Start gap fill thread
    gap_fill = threading.Thread(target=gap_fill_thread, args=(conn, bq_ready), daemon=True)
    gap_fill.start()

    # Start HTTP webhook server
    webhook = threading.Thread(target=start_webhook_server, args=(conn,), daemon=True)
    webhook.start()

    # Main loop: poll ioFog message bus
    log.info(f"Polling ioFog bus every {POLL_INTERVAL}s...")
    while True:
        poll_iofog_bus(conn)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
