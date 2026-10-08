#!/usr/bin/env python3
"""
BigQuery ML Anomaly Detection Runner
=====================================
Runs on GCP (either as a Cloud Function, Cloud Run service, or
as a scheduled script on the e2-micro VM).

Triggered by Cloud Scheduler via Pub/Sub every 6 hours.
Executes AI.DETECT_ANOMALIES on the sensor_readings table using
BigQuery ML's built-in TimesFM model, writes results to anomaly_scores table,
and publishes anomaly events to Pub/Sub for the ADK agent to process.

Deploy as Cloud Function:
  gcloud functions deploy anomaly-runner \
    --runtime=python311 --trigger-topic=smart-cooling-agent-triggers \
    --entry-point=run_anomaly_detection \
    --set-env-vars=PROJECT_ID=your-project,DATASET=cold_storage_lake
"""

import os
import json
import logging
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("anomaly-runner")

PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "")
DATASET    = os.environ.get("GCP_DATASET", "cold_storage_lake")
REGION     = os.environ.get("GCP_REGION", "asia-south1")
SA_KEY     = os.environ.get("GCP_SERVICE_ACCOUNT_KEY", "/app/gcp/service-account.json")

def get_bigquery_client():
    from google.cloud import bigquery
    from google.oauth2 import service_account
    if os.path.exists(SA_KEY):
        creds = service_account.Credentials.from_service_account_file(SA_KEY)
        return bigquery.Client(project=PROJECT_ID, credentials=creds)
    return bigquery.Client(project=PROJECT_ID)

def run_anomaly_detection(event=None, context=None):
    """
    Main entry point. Called by Cloud Scheduler → Pub/Sub.
    The event parameter contains the Pub/Sub message.
    """
    log.info("=" * 50)
    log.info("  BigQuery ML Anomaly Detection Runner")
    log.info("=" * 50)

    client = get_bigquery_client()

    # ─── 1. Run AI.DETECT_ANOMALIES on temperature ────────────────────────
    log.info("Running AI.DETECT_ANOMALIES on temperature...")
    temp_query = f"""
    INSERT INTO `{PROJECT_ID}.{DATASET}.anomaly_scores`
      (unitId, warehouseId, cloudScore, riskLevel, explanation, dominantSignal, evaluatedAt, modelVersion)
    WITH anomalies AS (
      SELECT
        unitId,
        warehouseId,
        is_anomaly,
        anomaly_probability,
        lower_bound,
        upper_bound
      FROM
        AI.DETECT_ANOMALIES(
          TABLE `{PROJECT_ID}.{DATASET}.sensor_readings`,
          STRUCT(
            0.85 AS anomaly_prob_threshold,
            'timestamp' AS time_series_timestamp_col,
            'temperature' AS time_series_data_col,
            'unitId' AS time_series_id_col
          )
        )
      WHERE timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
        AND is_anomaly = TRUE
    )
    SELECT
      a.unitId,
      a.warehouseId,
      a.anomaly_probability AS cloudScore,
      CASE
        WHEN a.anomaly_probability >= 0.85 THEN 'critical'
        WHEN a.anomaly_probability >= 0.65 THEN 'high'
        WHEN a.anomaly_probability >= 0.4  THEN 'warning'
        ELSE 'normal'
      END AS riskLevel,
      CONCAT('Temperature anomaly detected with probability ',
             CAST(ROUND(a.anomaly_probability, 3) AS STRING),
             '. Lower bound: ', CAST(ROUND(a.lower_bound, 2) AS STRING),
             '°C, Upper bound: ', CAST(ROUND(a.upper_bound, 2) AS STRING), '°C') AS explanation,
      'temperature' AS dominantSignal,
      CURRENT_TIMESTAMP() AS evaluatedAt,
      'bigquery-timesfm-v1' AS modelVersion
    FROM anomalies a
    """

    try:
        job = client.query(temp_query)
        job.result()
        rows_affected = job.num_dml_affected_rows
        log.info(f"Temperature anomaly detection: {rows_affected} anomalies found and inserted")
    except Exception as e:
        log.error(f"Temperature anomaly query failed: {e}")

    # ─── 2. Run AI.DETECT_ANOMALIES on energyConsumption ──────────────────
    log.info("Running AI.DETECT_ANOMALIES on energy consumption...")
    energy_query = f"""
    INSERT INTO `{PROJECT_ID}.{DATASET}.anomaly_scores`
      (unitId, warehouseId, cloudScore, riskLevel, explanation, dominantSignal, evaluatedAt, modelVersion)
    WITH anomalies AS (
      SELECT
        unitId,
        warehouseId,
        is_anomaly,
        anomaly_probability
      FROM
        AI.DETECT_ANOMALIES(
          TABLE `{PROJECT_ID}.{DATASET}.sensor_readings`,
          STRUCT(
            0.85 AS anomaly_prob_threshold,
            'timestamp' AS time_series_timestamp_col,
            'energyConsumption' AS time_series_data_col,
            'unitId' AS time_series_id_col
          )
        )
      WHERE timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
        AND is_anomaly = TRUE
    )
    SELECT
      a.unitId,
      a.warehouseId,
      a.anomaly_probability AS cloudScore,
      CASE
        WHEN a.anomaly_probability >= 0.85 THEN 'critical'
        WHEN a.anomaly_probability >= 0.65 THEN 'high'
        WHEN a.anomaly_probability >= 0.4  THEN 'warning'
        ELSE 'normal'
      END AS riskLevel,
      CONCAT('Energy consumption anomaly detected with probability ',
             CAST(ROUND(a.anomaly_probability, 3) AS STRING)) AS explanation,
      'energy' AS dominantSignal,
      CURRENT_TIMESTAMP() AS evaluatedAt,
      'bigquery-timesfm-v1' AS modelVersion
    FROM anomalies a
    """

    try:
        job = client.query(energy_query)
        job.result()
        rows_affected = job.num_dml_affected_rows
        log.info(f"Energy anomaly detection: {rows_affected} anomalies found and inserted")
    except Exception as e:
        log.error(f"Energy anomaly query failed: {e}")

    # ─── 3. Publish to Pub/Sub for ADK agent ──────────────────────────────
    log.info("Publishing anomaly events to Pub/Sub...")
    try:
        from google.cloud import pubsub_v1
        publisher = pubsub_v1.PublisherClient()
        topic_path = publisher.topic_path(PROJECT_ID, "smart-cooling-anomaly-alerts")

        # Get latest anomalies
        latest = client.query(f"""
            SELECT unitId, warehouseId, cloudScore, riskLevel, explanation, dominantSignal, evaluatedAt
            FROM `{PROJECT_ID}.{DATASET}.anomaly_scores`
            WHERE evaluatedAt > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 10 MINUTE)
            ORDER BY evaluatedAt DESC
            LIMIT 20
        """).result()

        for row in latest:
            event_data = {
                "unitId": row.unitId,
                "warehouseId": row.warehouseId,
                "cloudScore": float(row.cloudScore) if row.cloudScore else 0,
                "riskLevel": row.riskLevel,
                "explanation": row.explanation,
                "dominantSignal": row.dominantSignal,
                "evaluatedAt": str(row.evaluatedAt),
                "source": "bigquery_ml_timesfm"
            }
            publisher.publish(topic_path, json.dumps(event_data).encode("utf-8"))
            log.info(f"Published: {row.unitId} score={row.cloudScore} risk={row.riskLevel}")

    except Exception as e:
        log.warning(f"Pub/Sub publish failed (non-critical): {e}")

    # ─── 4. Summary ───────────────────────────────────────────────────────
    log.info("Anomaly detection complete.")
    log.info("=" * 50)
    return "OK"


if __name__ == "__main__":
    run_anomaly_detection()
