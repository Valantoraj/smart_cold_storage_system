"""
Ditto Tools — Tool definitions for ADK agents
================================================
Functions to query Eclipse Ditto digital twins for current state.
"""

import os
import logging
import requests
from typing import Dict, Optional, List

log = logging.getLogger("ditto-tools")

DITTO_URL     = os.environ.get("DITTO_URL", "http://ditto-gateway:8080")
DITTO_AUTH_H = "x-ditto-pre-authenticated"
DITTO_AUTH_V = "nginx:ditto"


def get_twin_state(unit_id: str) -> Dict:
    """
    Get the current digital twin state from Eclipse Ditto.
    Returns all features: temperature, humidity, compressor, energy,
    status, connectivity, maintenance, anomaly.
    
    Args:
        unit_id: Cold storage unit ID (e.g., CS-01)
    
    Returns:
        Full digital twin state with all feature properties
    """
    try:
        resp = requests.get(
            f"{DITTO_URL}/api/2/things/org.eclipse.ditto:{unit_id}",
            headers={DITTO_AUTH_H: DITTO_AUTH_V},
            timeout=10
        )
        if resp.status_code == 200:
            thing = resp.json()
            features = thing.get("features", {})
            return {
                "unitId": unit_id,
                "attributes": thing.get("attributes", {}),
                "temperature": features.get("temperature", {}).get("properties", {}),
                "humidity": features.get("humidity", {}).get("properties", {}),
                "compressor": features.get("compressor", {}).get("properties", {}),
                "energy": features.get("energy", {}).get("properties", {}),
                "status": features.get("status", {}).get("properties", {}),
                "connectivity": features.get("connectivity", {}).get("properties", {}),
                "maintenance": features.get("maintenance", {}).get("properties", {}),
                "anomaly": features.get("anomaly", {}).get("properties", {})
            }
        return {"error": f"Twin not found for {unit_id}", "status": resp.status_code}
    except Exception as e:
        return {"error": str(e)}


def get_all_twins_summary() -> List[Dict]:
    """
    Get a summary of all digital twins with their current health status.
    Uses Ditto's search API to query across all Things.
    
    Returns:
        List of all units with health, temperature, maintenance score, anomaly risk
    """
    try:
        resp = requests.get(
            f"{DITTO_URL}/api/2/search/things",
            headers={DITTO_AUTH_H: DITTO_AUTH_V},
            timeout=10
        )
        if resp.status_code != 200:
            return []

        data = resp.json()
        items = data if isinstance(data, list) else data.get("items", [])
        results = []
        for item in items:
            features = item.get("features", {})
            results.append({
                "unitId": item.get("thingId", "").split(":")[-1],
                "health": features.get("status", {}).get("properties", {}).get("health", "unknown"),
                "healthScore": features.get("status", {}).get("properties", {}).get("healthScore", 0),
                "temperature": features.get("temperature", {}).get("properties", {}).get("value"),
                "maintenanceScore": features.get("maintenance", {}).get("properties", {}).get("score", 0),
                "anomalyRisk": features.get("anomaly", {}).get("properties", {}).get("riskLevel", "unknown"),
                "anomalyEdgeScore": features.get("anomaly", {}).get("properties", {}).get("edgeScore"),
                "anomalyCloudScore": features.get("anomaly", {}).get("properties", {}).get("cloudScore"),
                "connected": features.get("connectivity", {}).get("properties", {}).get("connected", False)
            })
        return results
    except Exception as e:
        log.warning(f"Ditto search failed: {e}")
        return []


def get_maintenance_feature(unit_id: str) -> Dict:
    """
    Get the maintenance feature from a digital twin.
    
    Args:
        unit_id: Cold storage unit ID
    
    Returns:
        Maintenance score, recommendation, priority, and component scores
    """
    try:
        resp = requests.get(
            f"{DITTO_URL}/api/2/things/org.eclipse.ditto:{unit_id}/features/maintenance",
            headers={DITTO_AUTH_H: DITTO_AUTH_V},
            timeout=10
        )
        if resp.status_code == 200:
            return {"unitId": unit_id, **resp.json().get("properties", {})}
        return {"error": "Maintenance feature not found"}
    except Exception as e:
        return {"error": str(e)}
