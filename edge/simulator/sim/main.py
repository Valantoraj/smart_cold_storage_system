"""
sim/main.py — Sensor simulator main loop
=========================================
Publishes raw samples to coldstorage/<unit>/data every SIM_INTERVAL_S.
Subscribes to coldstorage/<unit>/control for fault injection.
"""

from __future__ import annotations
import json
import logging
import os
import signal
import sys
import time
import threading
from typing import Dict

import paho.mqtt.client as mqtt

from .model import UnitState, step, apply_command

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [sim] %(levelname)s %(message)s")
log = logging.getLogger("simulator")

MQTT_HOST    = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT    = int(os.environ.get("MQTT_PORT", "1883"))
INTERVAL_S   = float(os.environ.get("SIM_INTERVAL_S", "5"))
UNITS_ENV    = os.environ.get("UNITS", "CS-01,CS-02,CS-03")
START_FAULT  = os.environ.get("SIM_START_FAULT", "")

# Unit configs
UNIT_CFG = {
    "CS-01": {"setpoint_c": 4.0, "hard_limit_c": 8.0},
    "CS-02": {"setpoint_c": 4.0, "hard_limit_c": 8.0},
    "CS-03": {"setpoint_c": 5.0, "hard_limit_c": 8.0},
}

_states: Dict[str, UnitState] = {}
_interval_lock = threading.Lock()
_running = True


def _on_connect(client: mqtt.Client, userdata, flags, rc, props=None):
    if rc == 0:
        log.info("Connected to MQTT broker %s:%d", MQTT_HOST, MQTT_PORT)
        for uid in _states:
            topic = f"coldstorage/{uid}/control"
            client.subscribe(topic, qos=1)
            log.info("Subscribed to %s", topic)
    else:
        log.error("MQTT connect failed rc=%d", rc)


def _on_message(client: mqtt.Client, userdata, msg):
    try:
        cmd = json.loads(msg.payload.decode())
        uid = msg.topic.split("/")[1]
        if uid in _states:
            log.info("Control cmd for %s: %s", uid, cmd)
            apply_command(_states[uid], cmd)
    except Exception as e:
        log.warning("Bad control message: %s", e)


def _sim_loop(client: mqtt.Client, uid: str):
    global _running
    state = _states[uid]
    last = time.time()
    while _running:
        now = time.time()
        elapsed = now - last
        with _interval_lock:
            iv = INTERVAL_S
        if elapsed < iv:
            time.sleep(min(0.1, iv - elapsed))
            continue
        last = now
        sample = step(state, now)
        if sample is not None:
            payload = json.dumps(sample)
            client.publish(f"coldstorage/{uid}/data", payload, qos=1)
            log.debug("Published %s temp=%.2f", uid, sample["temp_c"])


def main():
    global _running

    unit_ids = [u.strip() for u in UNITS_ENV.split(",") if u.strip()]
    for i, uid in enumerate(unit_ids):
        cfg = UNIT_CFG.get(uid, {"setpoint_c": 4.0, "hard_limit_c": 8.0})
        state = UnitState(
            unit_id=uid,
            setpoint_c=cfg["setpoint_c"],
            hard_limit_c=cfg["hard_limit_c"],
        )
        state.seed(42 + i)
        _states[uid] = state
        if START_FAULT:
            apply_command(state, {"cmd": "inject", "fault": START_FAULT})

    # Connect MQTT
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                         client_id="cold-twin-simulator")
    client.on_connect = _on_connect
    client.on_message = _on_message

    log.info("Connecting to %s:%d ...", MQTT_HOST, MQTT_PORT)
    while True:
        try:
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
            break
        except Exception as e:
            log.warning("MQTT connect error: %s — retrying in 5s", e)
            time.sleep(5)

    client.loop_start()

    # Start one thread per unit
    threads = []
    for uid in unit_ids:
        t = threading.Thread(target=_sim_loop, args=(client, uid),
                             daemon=True, name=f"sim-{uid}")
        t.start()
        threads.append(t)

    def _shutdown(sig, frame):
        global _running
        log.info("Shutting down...")
        _running = False
        client.loop_stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    log.info("Simulator running — %d units, interval=%ss", len(unit_ids), INTERVAL_S)
    while _running:
        time.sleep(1)


if __name__ == "__main__":
    main()
