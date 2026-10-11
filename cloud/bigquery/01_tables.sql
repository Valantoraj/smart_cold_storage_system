-- Phase 4.1: BigQuery tables for Cold Twin
-- Dataset: coldstorage (location: US)
-- Run: bq query --use_legacy_sql=false < cloud/bigquery/01_tables.sql

-- 1. Raw telemetry (1-minute aggregates from fog)
CREATE TABLE IF NOT EXISTS `coldstorage.telemetry_1min` (
  ts                    TIMESTAMP  NOT NULL,
  unit_id               STRING     NOT NULL,
  source                STRING     NOT NULL,  -- 'live' | 'backfill'
  temp_avg_c            FLOAT64,
  temp_min_c            FLOAT64,
  temp_max_c            FLOAT64,
  humidity_avg_pct      FLOAT64,
  compressor_duty       FLOAT64,
  power_avg_kw          FLOAT64,
  on_power_avg_kw       FLOAT64,
  temp_slope_c_per_min  FLOAT64,
  health_state          STRING,
  health_score          INT64,
  sample_count          INT64,
  fog_node              STRING
)
PARTITION BY DATE(ts)
CLUSTER BY unit_id
OPTIONS (
  partition_expiration_days = 730,
  description = "1-minute telemetry aggregates from fog nodes"
);

-- 2. Events (alerts, faults, state changes)
CREATE TABLE IF NOT EXISTS `coldstorage.events` (
  ts          TIMESTAMP  NOT NULL,
  unit_id     STRING     NOT NULL,
  severity    STRING     NOT NULL,  -- 'INFO' | 'WARNING' | 'CRITICAL'
  code        STRING     NOT NULL,
  message     STRING,
  evidence    JSON,
  source      STRING,               -- 'edge' | 'fog' | 'cloud'
  resolved_at TIMESTAMP
)
PARTITION BY DATE(ts)
CLUSTER BY unit_id, severity
OPTIONS (description = "Alert and event log");

-- 3. Anomaly detection results (from BigQuery ML)
CREATE TABLE IF NOT EXISTS `coldstorage.anomaly_results` (
  ts              TIMESTAMP NOT NULL,
  unit_id         STRING    NOT NULL,
  metric          STRING    NOT NULL,  -- 'temp' | 'power'
  is_anomaly      BOOL,
  anomaly_prob    FLOAT64,
  lower_bound     FLOAT64,
  upper_bound     FLOAT64,
  actual_value    FLOAT64,
  model_version   STRING
)
PARTITION BY DATE(ts)
CLUSTER BY unit_id
OPTIONS (description = "BQML anomaly detection results");

-- 4. Work orders (maintenance actions from agent)
CREATE TABLE IF NOT EXISTS `coldstorage.work_orders` (
  work_order_id   STRING    NOT NULL,
  unit_id         STRING    NOT NULL,
  created_at      TIMESTAMP NOT NULL,
  urgency         STRING,             -- 'low' | 'medium' | 'high' | 'critical'
  action          STRING,
  description     STRING,
  status          STRING,             -- 'open' | 'acknowledged' | 'resolved'
  resolved_at     TIMESTAMP,
  agent_run_id    STRING
)
OPTIONS (description = "Maintenance work orders created by agent");

-- 5. Agent run log
CREATE TABLE IF NOT EXISTS `coldstorage.agent_runs` (
  run_id          STRING    NOT NULL,
  started_at      TIMESTAMP NOT NULL,
  completed_at    TIMESTAMP,
  trigger         STRING,
  units_evaluated ARRAY<STRING>,
  decisions       JSON,
  tool_trace      JSON,
  llm_failed      BOOL      DEFAULT FALSE,
  model_used      STRING
)
OPTIONS (description = "Maintenance agent execution log");
