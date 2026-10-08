#!/usr/bin/env python3
"""
Smart Cold Storage - Interactive Web Controller

Flask + SocketIO backend that runs the simulation engine, publishes to MQTT,
and pushes real-time data to the browser via WebSocket.
"""

import json, time, random, threading, os
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from collections import deque
import paho.mqtt.client as mqtt
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit

# ─── Flask ──────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["SECRET_KEY"] = "smart-cold-storage"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# ─── MQTT ───────────────────────────────────────────────────────────────────
MQTT_HOST = os.environ.get("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))
mqtt_client = mqtt.Client(client_id="web_controller")
mqtt_connected = False

def _on_connect(client, ud, flags, rc):
    global mqtt_connected
    mqtt_connected = (rc == 0)
    print(f"[MQTT] Connected={mqtt_connected}")

def _on_disconnect(client, ud, rc):
    global mqtt_connected
    mqtt_connected = False

mqtt_client.on_connect = _on_connect
mqtt_client.on_disconnect = _on_disconnect
try:
    mqtt_client.connect(MQTT_HOST, MQTT_PORT, 60)
    mqtt_client.loop_start()
except Exception as e:
    print(f"[MQTT] {e}")

# ─── Data ────────────────────────────────────────────────────────────────────
@dataclass
class SensorReading:
    unitId: str
    temperature: float
    humidity: float
    compressorStatus: str
    energyConsumption: float
    timestamp: str
    scenario: str = ""
    healthStatus: str = "healthy"
    alertType: str = ""

# ─── Unit Simulator ─────────────────────────────────────────────────────────
class ColdStorageUnit:
    SCENARIOS = [
        "normal","temp_rising","temp_fluctuating","high_energy",
        "humidity_issue","equipment_degradation","door_open","compressor_failure",
    ]
    SCENARIO_INFO = {
        "normal":                {"label":"Normal","color":"#059669","desc":"Stable operation"},
        "temp_rising":           {"label":"Temp Rising","color":"#d97706","desc":"Gradual increase"},
        "temp_fluctuating":      {"label":"Fluctuating","color":"#7c3aed","desc":"Erratic swings"},
        "high_energy":           {"label":"High Energy","color":"#d97706","desc":"Excess power draw"},
        "humidity_issue":        {"label":"Humidity Drift","color":"#0891b2","desc":"Moisture rising"},
        "equipment_degradation": {"label":"Degradation","color":"#dc2626","desc":"Multi-signal decline"},
        "door_open":            {"label":"Door Open","color":"#dc2626","desc":"Rapid temp+humidity spike"},
        "compressor_failure":   {"label":"Comp. Failure","color":"#dc2626","desc":"Compressor dead"},
    }

    def __init__(self, uid, location, scenario="normal"):
        self.unit_id = uid; self.location = location; self.scenario = scenario
        self.target_temp = 4.0; self.target_humidity = 65.0; self.base_energy = 2.0
        self.temperature = self.target_temp; self.humidity = self.target_humidity
        self.compressor_on = False; self.compressor_runtime = 0; self.compressor_cycles = 0
        self.energy_consumption = 0.0; self.step = 0; self.history = deque(maxlen=30)
        self.last_alert = None

    def _p(self):
        return {
            "normal":{"tv":0.2}, "temp_rising":{"tir":0.05},
            "temp_fluctuating":{"tv":1.0}, "high_energy":{"bem":1.5},
            "humidity_issue":{"hdr":0.5}, "equipment_degradation":{"tir":0.03},
            "door_open":{"tir":0.15,"hir":1.0}, "compressor_failure":{"tir":0.08},
        }.get(self.scenario, {"tv":0.2})

    def simulate(self) -> SensorReading:
        self.step += 1; p = self._p()

        if self.scenario == "normal":
            self.temperature += (random.uniform(-0.15,-0.05) if self.compressor_on else random.uniform(0.02,0.08))
            self.temperature += random.uniform(-0.2,0.2); self.temperature = max(2.0,min(6.0,self.temperature))
            self.humidity += random.uniform(-2,2); self.humidity = max(60,min(70,self.humidity))
        elif self.scenario == "temp_rising":
            self.temperature += p.get("tir",0.05)+random.uniform(-0.01,0.02)
            if self.compressor_on: self.temperature -= 0.03
            self.humidity += random.uniform(-1,2); self.humidity = max(60,min(75,self.humidity))
        elif self.scenario == "temp_fluctuating":
            self.temperature += random.uniform(-1,1)
            if self.step % 5 == 0: self.compressor_on = not self.compressor_on
            self.humidity += random.uniform(-3,3); self.humidity = max(55,min(75,self.humidity))
        elif self.scenario == "high_energy":
            if self.compressor_on: self.temperature -= random.uniform(0.05,0.15)
            else: self.temperature += random.uniform(0.02,0.08)
            self.temperature += random.uniform(-0.3,0.3); self.temperature = max(2.0,min(6.0,self.temperature))
            self.humidity += random.uniform(-2,2); self.humidity = max(60,min(70,self.humidity))
        elif self.scenario == "humidity_issue":
            self.temperature += random.uniform(-0.2,0.2)
            self.temperature = (self.temperature-0.08 if self.compressor_on else self.temperature+0.05)
            self.temperature = max(3.0,min(5.5,self.temperature))
            self.humidity += p.get("hdr",0.5)+random.uniform(-1,1); self.humidity = min(85,self.humidity)
        elif self.scenario == "equipment_degradation":
            self.temperature += p.get("tir",0.03)
            self.temperature += (-0.05 if self.compressor_on else 0.06)
            self.humidity += random.uniform(-2.5,2.5); self.humidity = max(62,min(72,self.humidity))
        elif self.scenario == "door_open":
            self.temperature += p.get("tir",0.15)+random.uniform(0,0.05)
            self.humidity += p.get("hir",1.0)+random.uniform(0,0.5)
            self.compressor_on = True; self.temperature = min(15.0,self.temperature); self.humidity = min(90,self.humidity)
        elif self.scenario == "compressor_failure":
            self.temperature += p.get("tir",0.08)+random.uniform(0,0.02)
            self.compressor_on = False; self.humidity += random.uniform(0.5,1.5); self.humidity = min(85,self.humidity)

        # Compressor thermostat
        if self.scenario not in ("compressor_failure","door_open"):
            if self.temperature > self.target_temp+0.5:
                if not self.compressor_on: self.compressor_on = True; self.compressor_cycles += 1
            elif self.temperature < self.target_temp-0.3: self.compressor_on = False
        if self.compressor_on: self.compressor_runtime += 1

        # Energy
        if self.scenario == "compressor_failure":
            self.energy_consumption = random.uniform(0.1,0.3)
        else:
            base = self.base_energy * (1.5 if self.scenario == "high_energy" else 1.0)
            if self.compressor_on:
                self.energy_consumption = base + random.uniform(0.3,0.7)
                if self.scenario in ("equipment_degradation","temp_rising","high_energy"):
                    self.energy_consumption += self.step * {"equipment_degradation":0.025,"temp_rising":0.02,"high_energy":0.03}[self.scenario]
                if self.temperature > self.target_temp+1.0: self.energy_consumption += 0.5
            else:
                self.energy_consumption = random.uniform(0.1,0.3)
            self.energy_consumption = min(5.0, self.energy_consumption)

        # Health + alert
        at = ""
        if self.temperature >= 10: at = "temperature_critical_high"
        elif self.temperature >= 8: at = "temperature_warning_high"
        elif self.humidity > 80 or self.humidity < 50: at = "humidity_out_of_range"
        elif self.energy_consumption >= 4: at = "energy_critical"
        elif self.energy_consumption >= 3: at = "energy_warning"

        health = "critical" if (self.temperature>=10 or self.energy_consumption>=4) else ("warning" if (self.temperature>=8 or self.energy_consumption>=3 or self.humidity>80 or self.humidity<50) else "healthy")

        r = SensorReading(self.unit_id, round(self.temperature,2), round(self.humidity,1),
                          "ON" if self.compressor_on else "OFF", round(self.energy_consumption,2),
                          datetime.now(timezone.utc).isoformat(), self.scenario, health, at)

        self.history.append({"temp":r.temperature,"humidity":r.humidity,"energy":r.energyConsumption,
                             "compressor":r.compressorStatus,"time":r.timestamp})

        new_alert = bool(at)
        if new_alert and self.last_alert != at: self.last_alert = at
        elif not new_alert: self.last_alert = None

        return r

    def set_scenario(self, s):
        if s in self.SCENARIOS: self.scenario = s; self.step = 0; return True
        return False

    def state(self):
        return {"unitId":self.unit_id,"location":self.location,"scenario":self.scenario,
                "temperature":round(self.temperature,2),"humidity":round(self.humidity,1),
                "compressorStatus":"ON" if self.compressor_on else "OFF",
                "energyConsumption":round(self.energy_consumption,2),
                "healthStatus":"critical" if self.temperature>=10 else ("warning" if self.temperature>=8 else "healthy"),
                "compressorCycles":self.compressor_cycles,"compressorRuntime":self.compressor_runtime,
                "history":list(self.history)}

def _alert_msg(r):
    msgs = {"temperature_critical_high":f"Temperature critically high: {r.temperature}°C",
            "temperature_warning_high":f"Temperature above normal: {r.temperature}°C",
            "humidity_out_of_range":f"Humidity out of range: {r.humidity}%",
            "energy_critical":f"Energy critically high: {r.energyConsumption}kW",
            "energy_warning":f"Energy elevated: {r.energyConsumption}kW"}
    return msgs.get(r.alertType,"Unknown alert")

# ─── Globals ────────────────────────────────────────────────────────────────
units = {
    "CS-01": ColdStorageUnit("CS-01","Warehouse A · Section 1","normal"),
    "CS-02": ColdStorageUnit("CS-02","Warehouse A · Section 2","normal"),
    "CS-03": ColdStorageUnit("CS-03","Warehouse B · Section 1","normal"),
}
sim_running = True; sim_speed = 1.0; sim_interval = 3.0
stats = {"messages_sent":0,"alerts_triggered":0,"start_time":time.time()}
alerts_log = deque(maxlen=50)
lock = threading.Lock()

# ─── Simulation Loop ────────────────────────────────────────────────────────
def sim_loop():
    global sim_running, sim_speed, stats
    while True:
        if not sim_running: time.sleep(1); continue
        with lock:
            for uid, u in units.items():
                r = u.simulate()
                payload = json.dumps({"unitId":r.unitId,"temperature":r.temperature,"humidity":r.humidity,
                                      "compressorStatus":r.compressorStatus,"energyConsumption":r.energyConsumption,
                                      "timestamp":r.timestamp})
                if mqtt_connected:
                    mqtt_client.publish(f"coldstorage/{uid}/data", payload, qos=1)
                    stats["messages_sent"] += 1
                if r.alertType:
                    ae = {"unitId":uid,"alertType":r.alertType,"severity":"critical" if "critical" in r.alertType else "warning",
                          "message":_alert_msg(r),"value":r.temperature if "temp" in r.alertType else r.energyConsumption,
                          "timestamp":r.timestamp,"scenario":r.scenario}
                    if not alerts_log or (alerts_log[0].get("alertType")!=r.alertType or alerts_log[0].get("unitId")!=uid):
                        alerts_log.appendleft(ae); stats["alerts_triggered"] += 1
                        socketio.emit("alert", ae)
                socketio.emit("reading",{**asdict(r),"location":u.location,
                               "compressorCycles":u.compressor_cycles,"compressorRuntime":u.compressor_runtime,
                               "history":list(u.history)})
        time.sleep(sim_interval / sim_speed)

threading.Thread(target=sim_loop, daemon=True).start()

# ─── Routes ────────────────────────────────────────────────────────────────
@app.route("/")
def index(): return render_template("index.html")

@app.route("/api/status")
def api_status():
    with lock: return jsonify({"running":sim_running,"speed":sim_speed,"mqttConnected":mqtt_connected,
                              "stats":stats,"units":{k:v.state() for k,v in units.items()},"alerts":list(alerts_log)[:20]})

@socketio.on("set_scenario")
def h_scenario(d):
    uid, sc = d.get("unitId"), d.get("scenario")
    with lock:
        if uid in units and units[uid].set_scenario(sc):
            emit("scenario_changed",{"unitId":uid,"scenario":sc},broadcast=True)

@socketio.on("control")
def h_control(d):
    global sim_running, sim_speed
    a = d.get("action")
    if a in ("stop","pause"): sim_running = False
    elif a == "start": sim_running = True
    elif a == "speed": sim_speed = float(d.get("speed",1.0))
    emit("control_changed",{"running":sim_running,"speed":sim_speed},broadcast=True)

@socketio.on("connect")
def h_connect():
    with lock:
        emit("init",{"running":sim_running,"speed":sim_speed,"mqttConnected":mqtt_connected,"stats":stats,
                     "units":{k:v.state() for k,v in units.items()},"alerts":list(alerts_log)[:20],
                     "scenarios":[{"id":s,**ColdStorageUnit.SCENARIO_INFO[s]} for s in ColdStorageUnit.SCENARIOS]})

if __name__ == "__main__":
    print("="*50)
    print("  Smart Cold Storage Web Controller")
    print(f"  MQTT: {MQTT_HOST}:{MQTT_PORT}")
    print("  URL:  http://0.0.0.0:8088")
    print("="*50)
    socketio.run(app, host="0.0.0.0", port=8088, debug=False, allow_unsafe_werkzeug=True)
