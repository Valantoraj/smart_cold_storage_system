"""
Simulator main loop for the cold-twin project.

One thread per cold-storage unit. Each thread:
  - Runs the physics model every SIM_INTERVAL_S seconds
  - Publishes sensor data to coldstorage/<unit>/data (QoS 1)
  - Subscribes to coldstorage/<unit>/control for fault injection / repair / config

Environment variables
---------------------
MQTT_HOST         broker hostname or IP (required)
MQTT_PORT         broker port (default 1883)
SIM_INTERVAL_S    publish interval in seconds (default 5)
UNITS             comma-separated unit IDs (default CS-01,CS-02,CS-03)
SIM_START_FAULT   optional fault to inject at startup, format: <unit>:<fault>
                  e.g.  CS-01:compressor_degradation
"""

from __future__ import annotations

import json
import logging
import os
import random
import threading
import time
from dataclasses import replace
from datetime import datetime, timezone
from typing import Optional

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from .model import (
    DT_S,
    UnitState,
    ambient_c,
    apply_fault,
    repair,
    step,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("sim.main")

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------

MQTT_HOST: str = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT: int = int(os.environ.get("MQTT_PORT", "1883"))
SIM_INTERVAL_S: float = float(os.environ.get("SIM_INTERVAL_S", "5"))
UNITS: list[str] = [u.strip() for u in os.environ.get("UNITS", "CS-01,CS-02,CS-03").split(",") if u.strip()]
SIM_START_FAULT: str = os.environ.get("SIM_START_FAULT", "")

# Default setpoint for all units (°C); could be extended per-unit
DEFAULT_SETPOINT_C: float = 4.0


# ---------------------------------------------------------------------------
# Per-unit simulator thread
# ---------------------------------------------------------------------------

class UnitSimulator(threading.Thread):
    """Runs the physics loop for one cold-storage unit and talks to MQTT."""

    def __init__(self, unit_id: str, start_fault: Optional[str] = None) -> None:
        super().__init__(name=f"sim-{unit_id}", daemon=True)
        self.unit_id = unit_id
        self._rng = random.Random()

        # Physics state
        self._state = UnitState(
            T=DEFAULT_SETPOINT_C,
            compressor_on=False,
            fault=None,
            RH=67.0,
            eff=1.0,
            seq=0,
            baseline_on_power_kw=2.0,
        )
        self._setpoint_c: float = DEFAULT_SETPOINT_C
        self._interval_s: float = SIM_INTERVAL_S

        # Fault tracking
        self._fault_name: Optional[str] = start_fault
        self._fault_start_s: Optional[float] = time.monotonic() if start_fault else None

        # MQTT client (one per unit to avoid shared-state contention)
        self._client = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id=f"sim-{unit_id}",
            clean_session=True,
        )
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect

        self._stop_event = threading.Event()

    # ------------------------------------------------------------------
    # MQTT callbacks
    # ------------------------------------------------------------------

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: object,
        connect_flags: object,
        reason_code: object,
        properties: object,
    ) -> None:
        if reason_code == 0:
            log.info("[%s] Connected to broker %s:%d", self.unit_id, MQTT_HOST, MQTT_PORT)
            topic = f"coldstorage/{self.unit_id}/control"
            client.subscribe(topic, qos=1)
            log.info("[%s] Subscribed to %s", self.unit_id, topic)
        else:
            log.warning("[%s] Connection failed: %s", self.unit_id, reason_code)

    def _on_disconnect(
        self,
        client: mqtt.Client,
        userdata: object,
        disconnect_flags: object,
        reason_code: object,
        properties: object,
    ) -> None:
        if reason_code != 0:
            log.warning("[%s] Unexpected disconnect (rc=%s), will auto-reconnect", self.unit_id, reason_code)

    def _on_message(
        self,
        client: mqtt.Client,
        userdata: object,
        message: mqtt.MQTTMessage,
    ) -> None:
        try:
            payload = json.loads(message.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            log.warning("[%s] Bad control message: %s", self.unit_id, exc)
            return

        cmd = payload.get("cmd", "")
        log.info("[%s] Control command received: %s", self.unit_id, payload)

        if cmd == "inject":
            fault = payload.get("fault")
            if fault:
                self._fault_name = fault
                self._fault_start_s = time.monotonic()
                log.info("[%s] Fault injected: %s", self.unit_id, fault)

        elif cmd == "repair":
            log.info("[%s] Repair requested", self.unit_id)
            # Gradual repair is applied in the main loop; flag removal of fault
            # by starting repair mode — we clear fault_name to stop apply_fault
            # but let the loop call repair() until eff==1.0
            self._fault_name = "__repairing__"
            self._fault_start_s = None

        elif cmd == "set":
            key = payload.get("key")
            value = payload.get("value")
            if key == "interval_s" and value is not None:
                self._interval_s = float(value)
                log.info("[%s] interval_s set to %s", self.unit_id, self._interval_s)
            elif key == "setpoint_c" and value is not None:
                self._setpoint_c = float(value)
                log.info("[%s] setpoint_c set to %s", self.unit_id, self._setpoint_c)
            else:
                log.warning("[%s] Unknown set key: %s", self.unit_id, key)

        else:
            log.warning("[%s] Unknown command: %s", self.unit_id, cmd)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        # Connect with automatic reconnect
        self._client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=60)
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._client.loop_start()

        while not self._stop_event.is_set():
            loop_start = time.monotonic()
            ts_utc = datetime.now(timezone.utc)

            # --- Advance physics ---
            self._state = step(self._state, self._setpoint_c, ts_utc, self._rng)

            # --- Apply fault / repair ---
            fault_elapsed_s = 0.0
            door_open_flag = False

            if self._fault_name == "__repairing__":
                self._state = repair(self._state)
                if self._state.fault is None:
                    # Repair complete
                    self._fault_name = None

            elif self._fault_name is not None:
                if self._fault_start_s is not None:
                    fault_elapsed_s = time.monotonic() - self._fault_start_s
                else:
                    fault_elapsed_s = 0.0

                self._state = apply_fault(self._state, self._fault_name, fault_elapsed_s)

                if self._fault_name == "door_open":
                    door_open_flag = fault_elapsed_s <= 180.0

            # --- Compute power for payload ---
            if self._state.compressor_on:
                power_kw = self._state.baseline_on_power_kw + self._rng.gauss(0.0, 0.05)
            else:
                power_kw = 0.15 + self._rng.gauss(0.0, 0.02)
            power_kw = max(0.0, power_kw)

            # --- Handle sensor dropout (T is None) ---
            raw_T = self._state.T
            if raw_T is None:
                # Don't publish when sensor is dropped out
                log.debug("[%s] Sensor dropout — skipping publish", self.unit_id)
            else:
                # --- Build and publish payload ---
                payload_dict = {
                    "schema": "v1",
                    "unit_id": self.unit_id,
                    "ts": ts_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "seq": self._state.seq,
                    "temp_c": round(float(raw_T), 3),
                    "humidity_pct": round(float(self._state.RH), 2),
                    "compressor_on": bool(self._state.compressor_on),
                    "power_kw": round(float(power_kw), 3),
                    "door_open": door_open_flag,
                }
                topic = f"coldstorage/{self.unit_id}/data"
                self._client.publish(topic, json.dumps(payload_dict), qos=1)
                log.debug("[%s] Published seq=%d T=%.2f°C", self.unit_id, self._state.seq, raw_T)

            # --- Sleep for remainder of interval ---
            elapsed = time.monotonic() - loop_start
            sleep_s = max(0.0, self._interval_s - elapsed)
            time.sleep(sleep_s)

        self._client.loop_stop()
        self._client.disconnect()
        log.info("[%s] Simulator stopped", self.unit_id)

    def stop(self) -> None:
        self._stop_event.set()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    log.info("Starting cold-twin simulator: units=%s broker=%s:%d", UNITS, MQTT_HOST, MQTT_PORT)

    # Parse optional start fault: "<unit>:<fault>"
    start_faults: dict[str, str] = {}
    if SIM_START_FAULT:
        try:
            unit_id, fault_name = SIM_START_FAULT.split(":", 1)
            start_faults[unit_id.strip()] = fault_name.strip()
            log.info("Start fault configured: unit=%s fault=%s", unit_id, fault_name)
        except ValueError:
            log.warning("SIM_START_FAULT format invalid (expected <unit>:<fault>): %s", SIM_START_FAULT)

    simulators: list[UnitSimulator] = []
    for unit_id in UNITS:
        fault = start_faults.get(unit_id)
        sim = UnitSimulator(unit_id=unit_id, start_fault=fault)
        sim.start()
        simulators.append(sim)

    # Block main thread; simulators are daemon threads but we keep main alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Shutdown requested")
        for sim in simulators:
            sim.stop()
        for sim in simulators:
            sim.join(timeout=5)
        log.info("All simulators stopped")


if __name__ == "__main__":
    main()
