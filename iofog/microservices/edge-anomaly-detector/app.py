#!/usr/bin/env python3
"""
Edge Anomaly Detector — Smart Cold Storage Digital Twin
=======================================================
Runs every 30 seconds on each edge node.
Queries local InfluxDB for recent sensor readings per unit,
computes a multi-variate anomaly score using:
  1. Z-score deviation from rolling 24h baseline (temp, humidity, energy)
  2. Pearson correlation between temperature and energy trends
  3. Compressor cycle frequency deviation from baseline

Score: 0.0 (normal) → 1.0 (critical anomaly)

Publishes scores to Node-RED webhook for local alerting
and to ioFog message bus for Ditto Sync Agent.
"""

import os
import time
import json
import math
import logging
import threading
import requests
import schedule
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple
from influxdb_client import InfluxDBClient
from influxdb_client.client.query_api import QueryApi

# ─── Configuration ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s"
)
log = logging.getLogger("edge-anomaly")

UNIT_IDS          = os.environ.get("UNIT_IDS", "CS-01,CS-02").split(",")
WAREHOUSE_ID      = os.environ.get("WAREHOUSE_ID", "alpha")
INFLUXDB_URL      = os.environ.get("INFLUXDB_URL", "http://influxdb:8086")
INFLUXDB_TOKEN    = os.environ.get("INFLUXDB_TOKEN", "smart-cooling-super-secret-token")
INFLUXDB_ORG      = os.environ.get("INFLUXDB_ORG", "smart_cooling")
INFLUXDB_BUCKET   = os.environ.get("INFLUXDB_BUCKET", "cold_storage")
SCAN_INTERVAL     = int(os.environ.get("SCAN_INTERVAL_SECONDS", "30"))
WARN_THRESHOLD    = float(os.environ.get("WARNING_THRESHOLD", "0.4"))
HIGH_THRESHOLD    = float(os.environ.get("HIGH_THRESHOLD", "0.65"))
CRIT_THRESHOLD    = float(os.environ.get("CRITICAL_THRESHOLD", "0.85"))
NODERED_WEBHOOK   = os.environ.get("NODERED_WEBHOOK_URL", "http://nodered:1880/webhook/anomaly")
IOFOG_BUS_URL     = os.environ.get("IOFOG_BUS_URL", "http://localhost:54321")

# How many readings to look back for trend analysis
TREND_WINDOW      = int(os.environ.get("TREND_WINDOW", "20"))
# How many hours for baseline calculation
BASELINE_HOURS    = int(os.environ.get("BASELINE_HOURS", "24"))


# ─── Data Classes ─────────────────────────────────────────────────────────────
@dataclass
class UnitBaseline:
    """Rolling 24h statistics for a unit"""
    unitId: str
    mean_temp: float = 4.0
    std_temp: float = 0.5
    mean_humidity: float = 65.0
    std_humidity: float = 3.0
    mean_energy: float = 2.0
    std_energy: float = 0.5
    baseline_compressor_pct: float = 50.0
    sample_count: int = 0
    last_updated: str = ""


@dataclass
class AnomalyScore:
    """Anomaly score result for one unit"""
    unitId: str
    warehouseId: str
    score: float
    riskLevel: str
    zscore_temp: float
    zscore_energy: float
    zscore_humidity: float
    correlation_score: float
    compressor_score: float
    explanation: str
    dominantSignal: str
    evaluatedAt: str
    trend_direction: str  # rising / falling / stable


# ─── InfluxDB Client ──────────────────────────────────────────────────────────
def create_influx_client() -> Optional[InfluxDBClient]:
    try:
        client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
        health = client.health()
        if health.status == "pass":
            log.info(f"InfluxDB connected: {INFLUXDB_URL}")
            return client
        else:
            log.warning(f"InfluxDB health check: {health.status}")
            return client
    except Exception as e:
        log.error(f"InfluxDB connection failed: {e}")
        return None


# ─── Baseline Computation ─────────────────────────────────────────────────────
def compute_baseline(query_api: QueryApi, unit_id: str) -> UnitBaseline:
    """
    Query last 24 hours of data and compute per-unit statistics.
    Returns default baseline if insufficient data.
    """
    baseline = UnitBaseline(unitId=unit_id, last_updated=datetime.now(timezone.utc).isoformat())

    flux = f'''
from(bucket: "{INFLUXDB_BUCKET}")
  |> range(start: -{BASELINE_HOURS}h)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> filter(fn: (r) => r["unitId"] == "{unit_id}")
  |> filter(fn: (r) => r["_field"] == "temperature" or
                       r["_field"] == "humidity" or
                       r["_field"] == "energyConsumption" or
                       r["_field"] == "compressorStatus")
  |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
'''

    try:
        tables = query_api.query(flux)
        temps, humidities, energies, compressor_ons = [], [], [], 0
        total_compressor = 0

        for table in tables:
            for record in table.records:
                temp = record.values.get("temperature")
                hum  = record.values.get("humidity")
                eng  = record.values.get("energyConsumption")
                comp = record.values.get("compressorStatus")

                if temp is not None: temps.append(float(temp))
                if hum  is not None: humidities.append(float(hum))
                if eng  is not None: energies.append(float(eng))
                if comp is not None:
                    total_compressor += 1
                    if str(comp) == "ON":
                        compressor_ons += 1

        count = len(temps)
        if count >= 10:
            baseline.mean_temp      = _mean(temps)
            baseline.std_temp       = max(_std(temps), 0.1)
            baseline.mean_humidity  = _mean(humidities) if humidities else 65.0
            baseline.std_humidity   = max(_std(humidities), 1.0) if humidities else 3.0
            baseline.mean_energy    = _mean(energies) if energies else 2.0
            baseline.std_energy     = max(_std(energies), 0.1) if energies else 0.5
            baseline.baseline_compressor_pct = (compressor_ons / total_compressor * 100) if total_compressor > 0 else 50.0
            baseline.sample_count   = count
            log.debug(f"Baseline {unit_id}: temp={baseline.mean_temp:.2f}±{baseline.std_temp:.2f}, "
                      f"energy={baseline.mean_energy:.2f}±{baseline.std_energy:.2f}, "
                      f"n={count}")
        else:
            log.info(f"Insufficient data for {unit_id} baseline ({count} points), using defaults")

    except Exception as e:
        log.warning(f"Baseline query failed for {unit_id}: {e}")

    return baseline


# ─── Recent Readings Query ────────────────────────────────────────────────────
def get_recent_readings(query_api: QueryApi, unit_id: str, n: int = 20) -> List[Dict]:
    """Get last N readings for a unit from InfluxDB"""
    flux = f'''
from(bucket: "{INFLUXDB_BUCKET}")
  |> range(start: -2h)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> filter(fn: (r) => r["unitId"] == "{unit_id}")
  |> filter(fn: (r) => r["_field"] == "temperature" or
                       r["_field"] == "humidity" or
                       r["_field"] == "energyConsumption" or
                       r["_field"] == "compressorStatus")
  |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> sort(columns: ["_time"], desc: true)
  |> limit(n: {n})
  |> sort(columns: ["_time"], desc: false)
'''
    readings = []
    try:
        tables = query_api.query(flux)
        for table in tables:
            for record in table.records:
                readings.append({
                    "time":              str(record.get_time()),
                    "temperature":       record.values.get("temperature"),
                    "humidity":          record.values.get("humidity"),
                    "energyConsumption": record.values.get("energyConsumption"),
                    "compressorStatus":  record.values.get("compressorStatus"),
                })
    except Exception as e:
        log.warning(f"Recent readings query failed for {unit_id}: {e}")
    return readings


# ─── Anomaly Scoring ──────────────────────────────────────────────────────────
def compute_anomaly_score(
    unit_id: str,
    readings: List[Dict],
    baseline: UnitBaseline
) -> AnomalyScore:
    """
    Multi-variate anomaly scoring:
    - Z-scores for temperature, humidity, energy (weighted)
    - Pearson correlation between temperature and energy trends
    - Compressor cycle frequency deviation
    """
    now = datetime.now(timezone.utc).isoformat()

    if len(readings) < 3:
        return AnomalyScore(
            unitId=unit_id, warehouseId=WAREHOUSE_ID, score=0.0,
            riskLevel="normal", zscore_temp=0.0, zscore_energy=0.0,
            zscore_humidity=0.0, correlation_score=0.0, compressor_score=0.0,
            explanation="Insufficient data", dominantSignal="none",
            evaluatedAt=now, trend_direction="stable"
        )

    # Extract valid values
    temps    = [r["temperature"]       for r in readings if r["temperature"] is not None]
    energies = [r["energyConsumption"] for r in readings if r["energyConsumption"] is not None]
    humids   = [r["humidity"]          for r in readings if r["humidity"] is not None]
    comps    = [r["compressorStatus"]  for r in readings if r["compressorStatus"] is not None]

    # ── 1. Z-score deviations (latest value vs baseline) ──────────────────
    zscore_temp = 0.0
    zscore_energy = 0.0
    zscore_humidity = 0.0

    if temps:
        latest_temp = temps[-1]
        zscore_temp = abs(latest_temp - baseline.mean_temp) / baseline.std_temp
        zscore_temp = min(zscore_temp / 3.0, 1.0)  # normalize: 3 sigma = 1.0

    if energies:
        latest_energy = energies[-1]
        zscore_energy = abs(latest_energy - baseline.mean_energy) / baseline.std_energy
        zscore_energy = min(zscore_energy / 3.0, 1.0)

    if humids:
        latest_humid = humids[-1]
        zscore_humidity = abs(latest_humid - baseline.mean_humidity) / baseline.std_humidity
        zscore_humidity = min(zscore_humidity / 3.0, 1.0)

    # ── 2. Temperature-Energy correlation ─────────────────────────────────
    correlation_score = 0.0
    trend_direction = "stable"

    if len(temps) >= 5 and len(energies) >= 5:
        n = min(len(temps), len(energies))
        t_window = temps[-n:]
        e_window = energies[-n:]

        corr = _pearson(t_window, e_window)
        temp_slope = _slope(t_window)
        energy_slope = _slope(e_window)

        # Both rising together is the key predictive maintenance signal
        if temp_slope > 0.01 and energy_slope > 0.005 and corr > 0.5:
            correlation_score = min(corr * 0.8 + 0.2, 1.0)
        elif temp_slope > 0.02:
            correlation_score = min(abs(temp_slope) * 10, 0.7)

        # Trend direction
        if temp_slope > 0.01:
            trend_direction = "rising"
        elif temp_slope < -0.01:
            trend_direction = "falling"

    # ── 3. Compressor cycle frequency ─────────────────────────────────────
    compressor_score = 0.0
    if len(comps) >= 4:
        on_pct = comps.count("ON") / len(comps) * 100

        # Deviation from baseline compressor percentage
        comp_deviation = abs(on_pct - baseline.baseline_compressor_pct)
        compressor_score = min(comp_deviation / 50.0, 1.0)

        # Count transitions (ON→OFF or OFF→ON)
        transitions = sum(1 for i in range(1, len(comps)) if comps[i] != comps[i-1])
        cycle_rate = transitions / len(comps)
        if cycle_rate > 0.4:  # excessive cycling
            compressor_score = min(compressor_score + 0.3, 1.0)

    # ── 4. Weighted composite score ────────────────────────────────────────
    score = (
        0.35 * zscore_temp +
        0.30 * zscore_energy +
        0.15 * zscore_humidity +
        0.15 * correlation_score +
        0.05 * compressor_score
    )
    score = min(max(score, 0.0), 1.0)

    # ── 5. Risk level ──────────────────────────────────────────────────────
    if score >= CRIT_THRESHOLD:
        risk = "critical"
    elif score >= HIGH_THRESHOLD:
        risk = "high"
    elif score >= WARN_THRESHOLD:
        risk = "warning"
    else:
        risk = "normal"

    # ── 6. Dominant signal and explanation ────────────────────────────────
    components = {
        "temperature": zscore_temp,
        "energy":      zscore_energy,
        "humidity":    zscore_humidity,
        "correlation": correlation_score,
        "compressor":  compressor_score,
    }
    dominant = max(components, key=components.get)

    explanation = _build_explanation(
        unit_id, score, risk, dominant,
        zscore_temp, zscore_energy, zscore_humidity,
        correlation_score, compressor_score,
        temps, energies, trend_direction, baseline
    )

    return AnomalyScore(
        unitId=unit_id,
        warehouseId=WAREHOUSE_ID,
        score=round(score, 4),
        riskLevel=risk,
        zscore_temp=round(zscore_temp, 4),
        zscore_energy=round(zscore_energy, 4),
        zscore_humidity=round(zscore_humidity, 4),
        correlation_score=round(correlation_score, 4),
        compressor_score=round(compressor_score, 4),
        explanation=explanation,
        dominantSignal=dominant,
        evaluatedAt=now,
        trend_direction=trend_direction,
    )


def _build_explanation(
    unit_id, score, risk, dominant,
    z_temp, z_energy, z_humidity,
    corr, comp,
    temps, energies, trend, baseline
) -> str:
    parts = []

    if temps:
        parts.append(f"Temp={temps[-1]:.1f}°C (baseline {baseline.mean_temp:.1f}±{baseline.std_temp:.1f})")
    if energies:
        parts.append(f"Energy={energies[-1]:.2f}kW (baseline {baseline.mean_energy:.1f}±{baseline.std_energy:.1f})")

    if dominant == "temperature":
        parts.append(f"Temperature anomaly: {z_temp:.2f}σ deviation")
    elif dominant == "energy":
        parts.append(f"Energy anomaly: {z_energy:.2f}σ deviation")
    elif dominant == "correlation":
        parts.append(f"Temperature+Energy both rising ({trend}): possible degradation")
    elif dominant == "compressor":
        parts.append(f"Compressor behavior anomaly: {comp:.2f} deviation score")

    if trend == "rising" and corr > 0.5:
        parts.append("Multi-signal rise detected: inspect refrigeration system")

    return " | ".join(parts)


# ─── Math Helpers ─────────────────────────────────────────────────────────────
def _mean(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0

def _std(values: List[float]) -> float:
    if len(values) < 2: return 0.1
    m = _mean(values)
    variance = sum((v - m) ** 2 for v in values) / len(values)
    return math.sqrt(variance) or 0.1

def _pearson(x: List[float], y: List[float]) -> float:
    n = min(len(x), len(y))
    if n < 3: return 0.0
    x, y = x[:n], y[:n]
    mx, my = _mean(x), _mean(y)
    num = sum((x[i] - mx) * (y[i] - my) for i in range(n))
    den = math.sqrt(sum((v - mx)**2 for v in x) * sum((v - my)**2 for v in y))
    return num / den if den > 0 else 0.0

def _slope(values: List[float]) -> float:
    """Simple linear regression slope"""
    n = len(values)
    if n < 2: return 0.0
    x = list(range(n))
    mx, my = _mean(x), _mean(values)
    num = sum((x[i] - mx) * (values[i] - my) for i in range(n))
    den = sum((v - mx) ** 2 for v in x)
    return num / den if den > 0 else 0.0


# ─── Event Publishing ─────────────────────────────────────────────────────────
def publish_to_nodered(anomaly: AnomalyScore):
    """Notify Node-RED via webhook for local alert handling"""
    try:
        payload = asdict(anomaly)
        requests.post(
            NODERED_WEBHOOK,
            json=payload,
            timeout=5
        )
        log.debug(f"Published to Node-RED: {anomaly.unitId} score={anomaly.score}")
    except Exception as e:
        log.debug(f"Node-RED webhook failed (non-critical): {e}")


def publish_to_iofog_bus(anomaly: AnomalyScore):
    """Publish score to ioFog message bus for Ditto Sync Agent"""
    try:
        payload = {
            "type": "anomaly_score",
            "data": asdict(anomaly)
        }
        requests.post(
            f"{IOFOG_BUS_URL}/v2/messages/new",
            json={"contentdata": json.dumps(payload), "infotype": "anomaly/score", "infoformat": "json"},
            timeout=5
        )
        log.debug(f"Published to ioFog bus: {anomaly.unitId} score={anomaly.score}")
    except Exception as e:
        log.debug(f"ioFog bus publish failed (non-critical): {e}")


def write_score_to_influxdb(client: InfluxDBClient, anomaly: AnomalyScore):
    """Write anomaly score back to local InfluxDB for Grafana display"""
    try:
        line = (
            f"anomaly_scores,"
            f"unitId={anomaly.unitId},"
            f"warehouseId={anomaly.warehouseId},"
            f"riskLevel={anomaly.riskLevel} "
            f"score={anomaly.score},"
            f"zscore_temp={anomaly.zscore_temp},"
            f"zscore_energy={anomaly.zscore_energy},"
            f"zscore_humidity={anomaly.zscore_humidity},"
            f"correlation_score={anomaly.correlation_score},"
            f"compressor_score={anomaly.compressor_score}"
        )
        write_api = client.write_api()
        write_api.write(bucket=INFLUXDB_BUCKET, record=line)
    except Exception as e:
        log.warning(f"Could not write anomaly score to InfluxDB: {e}")


# ─── Main Scan Loop ───────────────────────────────────────────────────────────
# Cache baselines to avoid recomputing every scan
_baselines: Dict[str, UnitBaseline] = {}
_baseline_last_updated: Dict[str, float] = {}
BASELINE_TTL = 6 * 3600  # recalculate every 6 hours


def run_scan(client: InfluxDBClient):
    """Run one full anomaly detection scan across all units"""
    query_api = client.query_api()
    now = time.time()

    for unit_id in UNIT_IDS:
        unit_id = unit_id.strip()
        try:
            # Refresh baseline if stale or missing
            if (unit_id not in _baselines or
                    now - _baseline_last_updated.get(unit_id, 0) > BASELINE_TTL):
                log.info(f"Computing baseline for {unit_id}...")
                _baselines[unit_id] = compute_baseline(query_api, unit_id)
                _baseline_last_updated[unit_id] = now

            baseline = _baselines[unit_id]

            # Get recent readings
            readings = get_recent_readings(query_api, unit_id, TREND_WINDOW)

            if not readings:
                log.debug(f"No recent readings for {unit_id}")
                continue

            # Compute score
            anomaly = compute_anomaly_score(unit_id, readings, baseline)

            log.info(
                f"{unit_id} | score={anomaly.score:.3f} | risk={anomaly.riskLevel} | "
                f"trend={anomaly.trend_direction} | dominant={anomaly.dominantSignal}"
            )

            # Publish based on severity
            if anomaly.score >= WARN_THRESHOLD:
                publish_to_nodered(anomaly)
                publish_to_iofog_bus(anomaly)
                log.warning(
                    f"ANOMALY [{anomaly.riskLevel.upper()}] {unit_id}: "
                    f"score={anomaly.score:.3f} — {anomaly.explanation}"
                )

            # Always write score to InfluxDB for Grafana
            write_score_to_influxdb(client, anomaly)

        except Exception as e:
            log.error(f"Error scanning {unit_id}: {e}", exc_info=True)


def main():
    log.info("=" * 60)
    log.info("  Edge Anomaly Detector — Smart Cold Storage")
    log.info("=" * 60)
    log.info(f"  Units     : {UNIT_IDS}")
    log.info(f"  Warehouse : {WAREHOUSE_ID}")
    log.info(f"  InfluxDB  : {INFLUXDB_URL}")
    log.info(f"  Interval  : {SCAN_INTERVAL}s")
    log.info(f"  Thresholds: warn={WARN_THRESHOLD}, high={HIGH_THRESHOLD}, crit={CRIT_THRESHOLD}")
    log.info("=" * 60)

    # Wait for InfluxDB to be ready
    client = None
    for attempt in range(20):
        client = create_influx_client()
        if client:
            break
        log.info(f"Waiting for InfluxDB... attempt {attempt + 1}/20")
        time.sleep(10)

    if not client:
        log.error("Could not connect to InfluxDB after 20 attempts. Exiting.")
        return

    # Schedule periodic scans
    schedule.every(SCAN_INTERVAL).seconds.do(run_scan, client=client)

    # Run immediately on startup
    log.info("Running initial scan...")
    run_scan(client)

    # Main loop
    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    main()
