-- =============================================================================
-- BigQuery Scheduled Queries — Smart Cold Storage Digital Twin
-- =============================================================================
-- These queries run on Cloud Scheduler triggers via Pub/Sub.
-- The BigQuery Streamer microservice executes them when triggered.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- QUERY 1: Hourly BigQuery ML Anomaly Detection (AI.DETECT_ANOMALIES)
-- Trigger: Cloud Scheduler every 6 hours → Pub/Sub → BigQuery Streamer
-- -----------------------------------------------------------------------------
INSERT INTO `${PROJECT_ID}.${DATASET}.anomaly_scores`
  (unitId, warehouseId, cloudScore, riskLevel, explanation, dominantSignal, evaluatedAt, modelVersion)

WITH raw_anomalies AS (
  SELECT
    unitId,
    warehouseId,
    is_anomaly,
    anomaly_probability,
    lower_bound,
    upper_bound,
    -- Determine dominant signal from subquery
    'temperature' AS dominantSignal,
    CURRENT_TIMESTAMP() AS evaluatedAt,
    'bigquery-timesfm-v1' AS modelVersion
  FROM
    AI.DETECT_ANOMALIES(
      TABLE `${PROJECT_ID}.${DATASET}.sensor_readings`,
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
  r.unitId,
  r.warehouseId,
  NULL AS edgeScore,
  r.anomaly_probability AS cloudScore,
  CASE
    WHEN r.anomaly_probability >= 0.85 THEN 'critical'
    WHEN r.anomaly_probability >= 0.65 THEN 'high'
    WHEN r.anomaly_probability >= 0.4  THEN 'warning'
    ELSE 'normal'
  END AS riskLevel,
  CONCAT('BigQuery ML detected anomaly in temperature with probability ',
         CAST(ROUND(r.anomaly_probability, 3) AS STRING)) AS explanation,
  r.dominantSignal,
  r.evaluatedAt,
  r.modelVersion
FROM raw_anomalies r;


-- -----------------------------------------------------------------------------
-- QUERY 2: Hourly Fleet Summary (for agent context)
-- Returns current status snapshot for all units
-- -----------------------------------------------------------------------------
SELECT
  unitId,
  warehouseId,
  AVG(temperature) AS avg_temp_1h,
  MAX(temperature) AS max_temp_1h,
  MIN(temperature) AS min_temp_1h,
  AVG(humidity) AS avg_humidity_1h,
  AVG(energyConsumption) AS avg_energy_1h,
  MAX(energyConsumption) AS max_energy_1h,
  COUNTIF(compressorStatus = 'ON') / COUNT(*) * 100 AS compressor_runtime_pct,
  COUNT(*) AS reading_count
FROM `${PROJECT_ID}.${DATASET}.sensor_readings`
WHERE timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
GROUP BY unitId, warehouseId
ORDER BY unitId;


-- -----------------------------------------------------------------------------
-- QUERY 3: 7-Day Unit Baselines (used by Edge Anomaly Detector calibration)
-- -----------------------------------------------------------------------------
SELECT
  unitId,
  AVG(temperature)       AS mean_temp,
  STDDEV(temperature)    AS std_temp,
  AVG(humidity)          AS mean_humidity,
  STDDEV(humidity)       AS std_humidity,
  AVG(energyConsumption) AS mean_energy,
  STDDEV(energyConsumption) AS std_energy,
  COUNTIF(compressorStatus = 'ON') / COUNT(*) * 100 AS baseline_compressor_pct
FROM `${PROJECT_ID}.${DATASET}.sensor_readings`
WHERE timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
GROUP BY unitId;


-- -----------------------------------------------------------------------------
-- QUERY 4: Alert Frequency Analysis (last 30 days)
-- Used by Maintenance Advisor agent tool
-- -----------------------------------------------------------------------------
SELECT
  unitId,
  alertType,
  severity,
  COUNT(*) AS alert_count,
  MIN(timestamp) AS first_seen,
  MAX(timestamp) AS last_seen,
  DATE_DIFF(MAX(timestamp), MIN(timestamp), DAY) AS days_span
FROM `${PROJECT_ID}.${DATASET}.alerts_history`
WHERE timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
GROUP BY unitId, alertType, severity
ORDER BY unitId, alert_count DESC;


-- -----------------------------------------------------------------------------
-- QUERY 5: Energy Efficiency Trend (for agent comparison tool)
-- -----------------------------------------------------------------------------
SELECT
  unitId,
  DATE(timestamp) AS date,
  AVG(energyConsumption) AS avg_energy,
  AVG(temperature)       AS avg_temp,
  -- Energy normalized by cooling load (lower is better)
  AVG(energyConsumption) / NULLIF(ABS(4.0 - AVG(temperature)) + 1, 0) AS efficiency_index
FROM `${PROJECT_ID}.${DATASET}.sensor_readings`
WHERE timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
GROUP BY unitId, DATE(timestamp)
ORDER BY unitId, date;
