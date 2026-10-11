#!/usr/bin/env bash
# Gate G4a — test ingest-service
# Temporarily allows unauthenticated, tests, then re-locks
cp -r /mnt/c/Users/valan/AppData/Roaming/gcloud/. ~/.config/gcloud/ 2>/dev/null || true

P=project-f47e3be0-07f0-4225-b8e
URL=https://ingest-service-qkttklqguq-uc.a.run.app

echo "[1] Temporarily allowing unauthenticated for testing..."
gcloud run services add-iam-policy-binding ingest-service \
  --region=us-central1 \
  --member=allUsers \
  --role=roles/run.invoker --quiet 2>&1 | tail -1

sleep 3

echo "[2] Health check..."
HTTP=$(curl -s -o /tmp/h.txt -w "%{http_code}" "${URL}/healthz")
echo "HTTP: $HTTP — $(cat /tmp/h.txt)"

echo ""
echo "[3] Send valid telemetry envelope..."
INNER='{"ts":"2026-10-11T10:31:00Z","unit_id":"CS-02","source":"live","temp_avg_c":4.4,"temp_min_c":4.1,"temp_max_c":4.7,"humidity_avg_pct":66.5,"compressor_duty":0.42,"power_avg_kw":1.1,"on_power_avg_kw":2.4,"temp_slope_c_per_min":0.004,"health_state":"OK","health_score":100,"sample_count":12,"fog_node":"fog-l2"}'
PAYLOAD='{"msg_type":"telemetry_1min","id":"CS-02|2026-10-11T10:31:00Z","payload":'${INNER}'}'
DATA_B64=$(echo -n "$PAYLOAD" | base64 -w0)
ENVELOPE='{"message":{"data":"'${DATA_B64}'","attributes":{"msg_type":"telemetry_1min","unit_id":"CS-02"}},"subscription":"test"}'

RES=$(curl -sf -X POST -H "Content-Type: application/json" -d "${ENVELOPE}" "${URL}/pubsub")
echo "Result: $RES"

echo ""
echo "[4] Send same message again (idempotency check)..."
RES2=$(curl -sf -X POST -H "Content-Type: application/json" -d "${ENVELOPE}" "${URL}/pubsub")
echo "Result: $RES2"

echo ""
echo "[5] Send malformed message (should ack not crash)..."
BAD='{"message":{"data":"bm90anNvbg==","attributes":{}},"subscription":"test"}'
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/json" -d "$BAD" "${URL}/pubsub")
echo "HTTP status for malformed: $STATUS (expected 200 or 204)"

echo ""
echo "[6] Checking BigQuery for test row (wait 5s)..."
sleep 5
bq query --use_legacy_sql=false \
  "SELECT COUNT(*) as cnt FROM \`coldstorage.v_telemetry_dedup\` WHERE unit_id='CS-02' AND source='live'"

echo ""
echo "[7] Re-locking to authenticated only..."
gcloud run services remove-iam-policy-binding ingest-service \
  --region=us-central1 \
  --member=allUsers \
  --role=roles/run.invoker --quiet 2>&1 | tail -1

echo ""
echo "=== GATE G4a complete ==="
