"""
cloud-bridge — Fog → Cloud Pub/Sub bridge with SQLite outbox
=============================================================
Subscribes to fog/cloud-outbox, buffers to SQLite, retries pub to GCP.
Also subscribes agent-actions-sub and delivers to coldstorage/<unit>/advice.

Env:
  MQTT_HOST          fog broker host (default: mosquitto-fog)
  MQTT_PORT          1883
  GCP_PROJECT_ID     GCP project
  TOPIC              coldstorage-telemetry
  SUBSCRIPTION       agent-actions-sub
  OUTBOX_PATH        /data/outbox.db
  GOOGLE_APPLICATION_CREDENTIALS  path to service account key (optional; use ADC if absent)
"""

from __future__ import annotations
import json
import logging
import os
import signal
import sqlite3
import sys
import threading
import time
import uuid
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [bridge] %(levelname)s %(message)s")
log = logging.getLogger("cloud-bridge")

MQTT_HOST    = os.environ.get("MQTT_HOST", "mosquitto-fog")
MQTT_PORT    = int(os.environ.get("MQTT_PORT", "1883"))
PROJECT_ID   = os.environ.get("GCP_PROJECT_ID", "project-f47e3be0-07f0-4225-b8e")
TOPIC_ID     = os.environ.get("TOPIC", "coldstorage-telemetry")
SUB_ID       = os.environ.get("SUBSCRIPTION", "agent-actions-sub")
OUTBOX_PATH  = os.environ.get("OUTBOX_PATH", "/data/outbox.db")
BATCH_SIZE   = int(os.environ.get("BATCH_SIZE", "20"))
FLUSH_INTERVAL = float(os.environ.get("FLUSH_INTERVAL_S", "5"))

_running = True
_mqtt_client: mqtt.Client | None = None


# ── Outbox (SQLite) ───────────────────────────────────────────────────────────

def _init_db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(OUTBOX_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(OUTBOX_PATH, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS outbox (
            id          TEXT PRIMARY KEY,
            msg_type    TEXT,
            unit_id     TEXT,
            payload     TEXT,
            created_at  TEXT,
            attempts    INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    return conn


def _enqueue(conn: sqlite3.Connection, envelope: dict):
    row_id = str(uuid.uuid4())
    conn.execute("""
        INSERT OR IGNORE INTO outbox (id, msg_type, unit_id, payload, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (
        row_id,
        envelope.get("msg_type", ""),
        envelope.get("payload", {}).get("unit_id", ""),
        json.dumps(envelope),
        datetime.now(timezone.utc).isoformat(),
    ))
    conn.commit()


def _dequeue_batch(conn: sqlite3.Connection) -> list[tuple]:
    rows = conn.execute(
        "SELECT id, payload FROM outbox ORDER BY created_at LIMIT ?",
        (BATCH_SIZE,)
    ).fetchall()
    return rows


def _delete_row(conn: sqlite3.Connection, row_id: str):
    conn.execute("DELETE FROM outbox WHERE id = ?", (row_id,))
    conn.commit()


def _increment_attempts(conn: sqlite3.Connection, row_id: str):
    conn.execute("UPDATE outbox SET attempts = attempts + 1 WHERE id = ?", (row_id,))
    conn.commit()


# ── Pub/Sub publisher ─────────────────────────────────────────────────────────

def _get_publisher():
    """Lazy-load google-cloud-pubsub publisher."""
    try:
        from google.cloud import pubsub_v1
        publisher = pubsub_v1.PublisherClient()
        topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)
        log.info("Pub/Sub publisher ready: %s", topic_path)
        return publisher, topic_path
    except ImportError:
        log.error("google-cloud-pubsub not installed")
        return None, None
    except Exception as e:
        log.error("Publisher init failed: %s", e)
        return None, None


def _publish_row(publisher, topic_path: str, envelope: dict) -> bool:
    try:
        payload_bytes = json.dumps(envelope).encode("utf-8")
        attrs = {
            "msg_type": envelope.get("msg_type", ""),
            "unit_id":  envelope.get("payload", {}).get("unit_id", ""),
        }
        future = publisher.publish(topic_path, payload_bytes, **attrs)
        future.result(timeout=10)
        return True
    except Exception as e:
        log.warning("Pub/Sub publish failed: %s", e)
        return False


# ── Agent-actions subscriber ──────────────────────────────────────────────────

def _agent_actions_loop():
    """Pull agent-actions-sub and forward advice to MQTT."""
    global _running
    try:
        from google.cloud import pubsub_v1
    except ImportError:
        log.warning("google-cloud-pubsub not available — agent actions disabled")
        return

    subscriber = pubsub_v1.SubscriberClient()
    sub_path = subscriber.subscription_path(PROJECT_ID, SUB_ID)
    log.info("Pulling from %s", sub_path)

    while _running:
        try:
            response = subscriber.pull(
                request={"subscription": sub_path, "max_messages": 5},
                timeout=10,
            )
            ack_ids = []
            for msg in response.received_messages:
                try:
                    data = json.loads(msg.message.data.decode())
                    unit_id = data.get("unit_id") or msg.message.attributes.get("unit_id", "")
                    if unit_id and _mqtt_client:
                        topic = f"coldstorage/{unit_id}/advice"
                        _mqtt_client.publish(topic, json.dumps(data), qos=1)
                        log.info("Forwarded advice to %s: action=%s", topic, data.get("action"))
                    ack_ids.append(msg.ack_id)
                except Exception as e:
                    log.warning("Failed to process agent action: %s", e)

            if ack_ids:
                subscriber.acknowledge(
                    request={"subscription": sub_path, "ack_ids": ack_ids}
                )
        except Exception as e:
            if _running:
                log.debug("Pull loop error: %s", e)
            time.sleep(5)


# ── MQTT callbacks ────────────────────────────────────────────────────────────

def _make_mqtt_client(db: sqlite3.Connection) -> mqtt.Client:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                         client_id="cold-twin-bridge")

    def on_connect(c, ud, flags, rc, props=None):
        if rc == 0:
            log.info("Connected to MQTT broker %s:%d", MQTT_HOST, MQTT_PORT)
            c.subscribe("fog/cloud-outbox", qos=1)
            log.info("Subscribed to fog/cloud-outbox")
        else:
            log.error("MQTT connect failed rc=%d", rc)

    def on_message(c, ud, msg):
        try:
            envelope = json.loads(msg.payload.decode())
            _enqueue(db, envelope)
        except Exception as e:
            log.warning("Bad outbox message: %s", e)

    client.on_connect = on_connect
    client.on_message = on_message
    return client


# ── Flush loop ────────────────────────────────────────────────────────────────

def _flush_loop(db: sqlite3.Connection):
    publisher, topic_path = _get_publisher()
    consecutive_fail = 0

    while _running:
        time.sleep(FLUSH_INTERVAL)
        if publisher is None:
            publisher, topic_path = _get_publisher()
            if publisher is None:
                continue

        rows = _dequeue_batch(db)
        if not rows:
            continue

        for row_id, payload_str in rows:
            try:
                envelope = json.loads(payload_str)
            except Exception:
                _delete_row(db, row_id)
                continue

            ok = _publish_row(publisher, topic_path, envelope)
            if ok:
                _delete_row(db, row_id)
                consecutive_fail = 0
                log.debug("Published %s → Pub/Sub", row_id[:8])
            else:
                _increment_attempts(db, row_id)
                consecutive_fail += 1
                if consecutive_fail > 10:
                    time.sleep(min(60, consecutive_fail * 2))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    global _running, _mqtt_client

    db = _init_db()
    log.info("Outbox DB: %s", OUTBOX_PATH)

    _mqtt_client = _make_mqtt_client(db)

    # Connect MQTT with retry
    while True:
        try:
            _mqtt_client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
            break
        except Exception as e:
            log.warning("MQTT connect error: %s — retrying in 5s", e)
            time.sleep(5)

    _mqtt_client.loop_start()

    # Flush thread
    flush_t = threading.Thread(target=_flush_loop, args=(db,), daemon=True, name="flush")
    flush_t.start()

    # Agent actions thread
    agent_t = threading.Thread(target=_agent_actions_loop, daemon=True, name="agent-actions")
    agent_t.start()

    def _shutdown(sig, frame):
        global _running
        log.info("Shutting down...")
        _running = False
        _mqtt_client.loop_stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    log.info("Cloud bridge running — project=%s topic=%s", PROJECT_ID, TOPIC_ID)
    while _running:
        time.sleep(1)


if __name__ == "__main__":
    main()
