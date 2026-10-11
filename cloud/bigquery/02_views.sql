-- Phase 4.1: BigQuery views for Cold Twin
-- Run after 01_tables.sql

-- Deduplicated telemetry (idempotent ingestion by unit_id + ts)
CREATE OR REPLACE VIEW `coldstorage.v_telemetry_dedup` AS
SELECT * EXCEPT(row_num)
FROM (
  SELECT *,
    ROW_NUMBER() OVER (PARTITION BY unit_id, ts ORDER BY ts DESC) AS row_num
  FROM `coldstorage.telemetry_1min`
)
WHERE row_num = 1;

-- Last known state per unit
CREATE OR REPLACE VIEW `coldstorage.v_unit_latest` AS
SELECT * EXCEPT(row_num)
FROM (
  SELECT *,
    ROW_NUMBER() OVER (PARTITION BY unit_id ORDER BY ts DESC) AS row_num
  FROM `coldstorage.v_telemetry_dedup`
)
WHERE row_num = 1;

-- Recent anomalies (last 24 hours)
CREATE OR REPLACE VIEW `coldstorage.v_anomalies_recent` AS
SELECT *
FROM `coldstorage.anomaly_results`
WHERE ts > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
  AND is_anomaly = TRUE
ORDER BY ts DESC;

-- Open work orders
CREATE OR REPLACE VIEW `coldstorage.v_open_work_orders` AS
SELECT *
FROM `coldstorage.work_orders`
WHERE status IN ('open', 'acknowledged')
ORDER BY created_at DESC;

-- Z-score anomaly fallback (pure SQL, no BQML needed)
CREATE OR REPLACE VIEW `coldstorage.v_zscore_anomalies` AS
WITH stats AS (
  SELECT
    unit_id,
    AVG(temp_avg_c)          AS mean_temp,
    STDDEV(temp_avg_c)       AS std_temp,
    AVG(power_avg_kw)        AS mean_power,
    STDDEV(power_avg_kw)     AS std_power
  FROM `coldstorage.v_telemetry_dedup`
  WHERE ts > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
  GROUP BY unit_id
),
scored AS (
  SELECT
    t.ts, t.unit_id, t.temp_avg_c, t.power_avg_kw,
    ABS((t.temp_avg_c  - s.mean_temp)  / NULLIF(s.std_temp,  0)) AS temp_zscore,
    ABS((t.power_avg_kw - s.mean_power) / NULLIF(s.std_power, 0)) AS power_zscore
  FROM `coldstorage.v_telemetry_dedup` t
  JOIN stats s USING (unit_id)
  WHERE t.ts > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
)
SELECT *,
  (temp_zscore > 3.0 OR power_zscore > 3.0) AS is_anomaly
FROM scored
ORDER BY ts DESC;
