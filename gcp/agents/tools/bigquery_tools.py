"""
BigQuery Tools — Tool definitions for ADK agents
==================================================
These functions are wrapped as ADK tools that the Gemini agent
can call via function calling. Each tool returns structured data
that the agent uses to reason about cold storage fleet health.
"""

import os
import logging
from typing import Dict, List, Optional
from google.cloud import bigquery
from google.oauth2 import service_account

log = logging.getLogger("bigquery-tools")

PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "")
DATASET    = os.environ.get("GCP_DATASET", "cold_storage_lake")
SA_KEY    = os.environ.get("GCP_SERVICE_ACCOUNT_KEY", "/app/gcp/service-account.json")

_bq_client = None

def _get_client():
    global _bq_client
    if _bq_client is None:
        if os.path.exists(SA_KEY):
            creds = service_account.Credentials.from_service_account_file(SA_KEY)
            _bq_client = bigquery.Client(project=PROJECT_ID, credentials=creds)
        else:
            _bq_client = bigquery.Client(project=PROJECT_ID)
    return _bq_client


def query_sensor_history(unit_id: str, metric: str = "temperature",
                          hours: int = 24) -> List[Dict]:
    """
    Query historical sensor data for a specific unit and metric.
    
    Args:
        unit_id: Cold storage unit ID (e.g., CS-01, CS-02, CS-03)
        metric: Which sensor metric to retrieve (temperature, humidity, energyConsumption)
        hours: How many hours of history to retrieve (default 24)
    
    Returns:
        List of readings with timestamp and value, plus summary statistics
    """
    client = _get_client()
    query = f"""
        SELECT timestamp, {metric} as value
        FROM `{PROJECT_ID}.{DATASET}.sensor_readings`
        WHERE unitId = '{unit_id}'
          AND timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {hours} HOUR)
        ORDER BY timestamp ASC
        LIMIT 1000
    """
    rows = list(client.query(query).result())
    values = [{"timestamp": str(r.timestamp), "value": float(r.value)} for r in rows if r.value is not None]

    if not values:
        return {"unitId": unit_id, "metric": metric, "count": 0, "message": "No data found"}

    vals = [v["value"] for v in values]
    return {
        "unitId": unit_id,
        "metric": metric,
        "count": len(values),
        "summary": {
            "min": min(vals),
            "max": max(vals),
            "mean": round(sum(vals)/len(vals), 3),
            "first": values[0],
            "last": values[-1]
        },
        "readings": values[-20:]
    }


def compute_trend(unit_id: str, metric: str = "temperature",
                   window_hours: int = 6) -> Dict:
    """
    Compute the trend (slope) of a metric over a time window.
    Positive slope = increasing, negative = decreasing, near zero = stable.
    
    Args:
        unit_id: Cold storage unit ID
        metric: Which metric to analyze (temperature, energyConsumption)
        window_hours: Time window for trend analysis (default 6 hours)
    
    Returns:
        Trend analysis with slope, direction, and rate of change
    """
    client = _get_client()
    query = f"""
        SELECT timestamp, {metric} as value
        FROM `{PROJECT_ID}.{DATASET}.sensor_readings`
        WHERE unitId = '{unit_id}'
          AND timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {window_hours} HOUR)
        ORDER BY timestamp ASC
    """
    rows = list(client.query(query).result())
    values = [(i, float(r.value)) for i, r in enumerate(rows) if r.value is not None]

    if len(values) < 5:
        return {"unitId": unit_id, "metric": metric, "trend": "insufficient_data", "slope": 0}

    n = len(values)
    x = [v[0] for v in values]
    y = [v[1] for v in values]
    mx, my = sum(x)/n, sum(y)/n
    num = sum((x[i]-mx)*(y[i]-my) for i in range(n))
    den = sum((v-mx)**2 for v in x)
    slope = num/den if den > 0 else 0

    direction = "rising" if slope > 0.01 else "falling" if slope < -0.01 else "stable"
    rate_per_hour = slope * (len(values) / window_hours)

    return {
        "unitId": unit_id,
        "metric": metric,
        "trend": direction,
        "slope": round(slope, 6),
        "rate_per_hour": round(rate_per_hour, 4),
        "window_hours": window_hours,
        "sample_count": n,
        "first_value": round(values[0][1], 2),
        "last_value": round(values[-1][1], 2),
        "change": round(values[-1][1] - values[0][1], 2)
    }


def get_anomaly_scores(unit_id: Optional[str] = None, hours: int = 24) -> List[Dict]:
    """
    Retrieve BigQuery ML anomaly detection scores from the anomaly_scores table.
    
    Args:
        unit_id: Specific unit to query (optional — if omitted, returns all units)
        hours: How many hours of scores to retrieve (default 24)
    
    Returns:
        List of anomaly scores with unitId, cloudScore, edgeScore, riskLevel
    """
    client = _get_client()
    unit_filter = f"AND unitId = '{unit_id}'" if unit_id else ""
    query = f"""
        SELECT unitId, warehouseId, edgeScore, cloudScore, riskLevel,
               explanation, dominantSignal, evaluatedAt, modelVersion
        FROM `{PROJECT_ID}.{DATASET}.anomaly_scores`
        WHERE evaluatedAt > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {hours} HOUR)
        {unit_filter}
        ORDER BY evaluatedAt DESC
        LIMIT 50
    """
    rows = list(client.query(query).result())
    return [{
        "unitId": r.unitId,
        "warehouseId": r.warehouseId,
        "edgeScore": float(r.edgeScore) if r.edgeScore else None,
        "cloudScore": float(r.cloudScore) if r.cloudScore else None,
        "riskLevel": r.riskLevel,
        "explanation": r.explanation,
        "dominantSignal": r.dominantSignal,
        "evaluatedAt": str(r.evaluatedAt),
        "modelVersion": r.modelVersion
    } for r in rows]


def get_alert_history(unit_id: str, hours: int = 24) -> List[Dict]:
    """
    Retrieve alert history for a specific cold storage unit.
    
    Args:
        unit_id: Cold storage unit ID
        hours: How many hours of alerts to retrieve (default 24)
    
    Returns:
        List of alerts with type, severity, message, value, threshold, timestamp
    """
    client = _get_client()
    query = f"""
        SELECT unitId, alertType, severity, message, value, threshold, timestamp
        FROM `{PROJECT_ID}.{DATASET}.alerts_history`
        WHERE unitId = '{unit_id}'
          AND timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {hours} HOUR)
        ORDER BY timestamp DESC
        LIMIT 50
    """
    rows = list(client.query(query).result())
    return [{
        "unitId": r.unitId,
        "alertType": r.alertType,
        "severity": r.severity,
        "message": r.message,
        "value": float(r.value) if r.value else None,
        "threshold": float(r.threshold) if r.threshold else None,
        "timestamp": str(r.timestamp)
    } for r in rows]


def compare_units(metric: str = "temperature", days: int = 7) -> List[Dict]:
    """
    Compare a metric across all cold storage units for a given time period.
    
    Args:
        metric: Which metric to compare (temperature, energyConsumption, humidity)
        days: How many days to include in the comparison (default 7)
    
    Returns:
        Per-unit comparison with mean, min, max, std for the metric
    """
    client = _get_client()
    query = f"""
        SELECT
            unitId,
            warehouseId,
            AVG({metric}) as mean_val,
            MIN({metric}) as min_val,
            MAX({metric}) as max_val,
            STDDEV({metric}) as std_val,
            COUNT(*) as reading_count
        FROM `{PROJECT_ID}.{DATASET}.sensor_readings`
        WHERE timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {days} DAY)
        GROUP BY unitId, warehouseId
        ORDER BY unitId
    """
    rows = list(client.query(query).result())
    return [{
        "unitId": r.unitId,
        "warehouseId": r.warehouseId,
        "metric": metric,
        "mean": round(float(r.mean_val), 3) if r.mean_val else 0,
        "min": round(float(r.min_val), 3) if r.min_val else 0,
        "max": round(float(r.max_val), 3) if r.max_val else 0,
        "std": round(float(r.std_val), 3) if r.std_val else 0,
        "reading_count": r.reading_count,
        "days": days
    } for r in rows]


def rank_units_by_maintenance_urgency() -> List[Dict]:
    """
    Rank all cold storage units by maintenance urgency based on
    anomaly scores, alert frequency, and trend analysis.
    
    Returns:
        Units ranked from most urgent to least urgent with reasoning
    """
    client = _get_client()
    query = f"""
        WITH latest_scores AS (
            SELECT unitId, warehouseId, cloudScore, riskLevel,
                   ROW_NUMBER() OVER (PARTITION BY unitId ORDER BY evaluatedAt DESC) as rn
            FROM `{PROJECT_ID}.{DATASET}.anomaly_scores`
            WHERE evaluatedAt > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 48 HOUR)
        ),
        alert_counts AS (
            SELECT unitId, COUNT(*) as alert_count
            FROM `{PROJECT_ID}.{DATASET}.alerts_history`
            WHERE timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
            GROUP BY unitId
        )
        SELECT
            l.unitId,
            l.warehouseId,
            COALESCE(l.cloudScore, 0) as cloud_score,
            l.riskLevel,
            COALESCE(a.alert_count, 0) as alert_count_24h
        FROM latest_scores l
        LEFT JOIN alert_counts a ON l.unitId = a.unitId
        WHERE l.rn = 1
        ORDER BY cloud_score DESC
    """
    rows = list(client.query(query).result())
    results = []
    for i, r in enumerate(rows):
        urgency = "critical" if r.cloud_score >= 0.85 else \
                  "high" if r.cloud_score >= 0.65 else \
                  "medium" if r.cloud_score >= 0.4 else "low"
        results.append({
            "rank": i + 1,
            "unitId": r.unitId,
            "warehouseId": r.warehouseId,
            "cloudScore": round(float(r.cloud_score), 3) if r.cloud_score else 0,
            "riskLevel": r.riskLevel,
            "alerts24h": r.alert_count_24h,
            "urgency": urgency,
            "recommendation": _urgency_recommendation(urgency, r.unitId)
        })
    return results


def _urgency_recommendation(urgency: str, unit_id: str) -> str:
    recs = {
        "critical": f"IMMEDIATE inspection required for {unit_id}. Schedule maintenance within 24 hours.",
        "high": f"Schedule maintenance for {unit_id} within 48 hours. Monitor closely.",
        "medium": f"Monitor {unit_id} trends. Schedule inspection within 2 weeks.",
        "low": f"{unit_id} operating normally. Routine maintenance schedule."
    }
    return recs.get(urgency, "Monitor")
