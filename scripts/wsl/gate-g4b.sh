#!/usr/bin/env bash
cp -r /mnt/c/Users/valan/AppData/Roaming/gcloud/. ~/.config/gcloud/ 2>/dev/null || true

echo "=== Gate G4b: Row count check ==="
bq query --use_legacy_sql=false \
  "SELECT COUNT(*) as total, COUNTIF(source='backfill') as backfill_rows FROM \`coldstorage.telemetry_1min\`"

echo ""
echo "=== Gate G4b: Z-score anomaly check on last 7 days ==="
bq query --use_legacy_sql=false \
  "SELECT COUNT(*) as total, COUNTIF(is_anomaly) as anomalies, ROUND(COUNTIF(is_anomaly)/COUNT(*)*100,2) as pct FROM \`coldstorage.v_zscore_anomalies\`"

echo ""
echo "=== Gate G4b: PASS if backfill=21600, anomaly_pct <= 2.0 ==="
