# Looker Studio Dashboard Configuration

Looker Studio provides a shareable, no-login dashboard connected directly
to BigQuery. Anyone with the URL can view it without Docker, Grafana, or
any technical setup.

## Setup Steps

### 1. Open Looker Studio

Go to: https://lookerstudio.google.com

Sign in with your Google account (same one as GCP project).

### 2. Create New Report

Click "Create" → "Report"

### 3. Connect to BigQuery

1. Click "Create data source"
2. Select "Google BigQuery" connector
3. Authorize access to your GCP project
4. Select project: `project-f47e3be0-07f0-4225-b8e`
5. Select dataset: `cold_storage_lake`
6. Select table: `sensor_readings`
7. Click "Connect"

### 4. Available Fields

After connection, these fields are available:
- `unitId` (dimension) — CS-01, CS-02, CS-03
- `warehouseId` (dimension) — alpha, beta
- `temperature` (metric)
- `humidity` (metric)
- `energyConsumption` (metric)
- `compressorStatus` (dimension)
- `timestamp` (date dimension)

### 5. Build These Charts

#### Chart 1: Temperature Time Series (line chart)
- Dimension: timestamp
- Metric: temperature (AVG)
- Breakdown: unitId
- Style: 3 colored lines, smooth curves
- Date range: last 7 days

#### Chart 2: Energy Consumption Comparison (bar chart)
- Dimension: unitId
- Metric: energyConsumption (AVG)
- Sort: descending by energyConsumption
- Style: color by temperature, green/yellow/red

#### Chart 3: Alert Summary (table)
- Connect to `alerts_history` table
- Dimensions: unitId, alertType, severity
- Metric: Record Count
- Sort: by timestamp DESC
- Filter: timestamp > last 30 days

#### Chart 4: Anomaly Score Trend (line chart)
- Connect to `anomaly_scores` table
- Dimension: evaluatedAt
- Metric: cloudScore (AVG)
- Breakdown: unitId
- Reference line at 0.65 (high risk threshold)

#### Chart 5: Fleet Status Scorecard (scorecard)
- Connect to `sensor_readings` table
- Metric: COUNT DISTINCT unitId
- Label: "Active Units"

#### Chart 6: Compressor Runtime (pie chart)
- Dimension: compressorStatus
- Metric: Record Count
- Filter: last 1 hour

### 6. Share

1. Click "Share" (top right)
2. Set "Anyone with link" → "Viewer"
3. Copy the shareable URL
4. Add URL to your README and .env:

```
LOOKER_STUDIO_URL=https://lookerstudio.google.com/reporting/your-report-id
```

### 7. Auto-refresh

Looker Studio refreshes data automatically every 15 minutes.
For faster updates, use the "Refresh data" button manually.

## Multiple Data Sources

Connect these BigQuery tables in the same report:
- `sensor_readings` — main sensor data
- `alerts_history` — alert log
- `anomaly_scores` — ML anomaly detection results
- `fleet_reports` — daily AI report history

## Branding

Set report title to "Smart Cold Storage — Fleet Intelligence"
Add your logo and use the color scheme:
- Background: #f0f4f8
- Cards: #ffffff with border #e2e8f0
- Accent: #2563eb
- Success: #059669, Warning: #d97706, Danger: #dc2626
