#!/usr/bin/env bash
set -e
cp -r /mnt/c/Users/valan/AppData/Roaming/gcloud/. ~/.config/gcloud/ 2>/dev/null || true

URL="https://ingest-service-405914735554.us-central1.run.app"
TOKEN=$(gcloud auth print-identity-token)

echo "=== Gate G4a: Testing ingest-service ==="
echo "URL: $URL"
echo ""

# 1. Health check
echo "[1] Health check..."
curl -sf -H "Authorization: Bearer ${TOKEN}" "${URL}/healthz"
echo ""

# 2. Valid telemetry envelope
echo ""
echo "[2] Send valid telemetry via POST /pubsub..."
INNER='{"ts":"2026-10-11T10:31:00Z","unit_id":"CS-02","source":"live","temp_avg_c":4.4,"temp_min_c":4.1,"temp_max_c":4.7,"humidity_avg_pct":66.5,"compressor_duty":0.42,"power_avg_kw":1.1,"on_power_avg_kw":2.4,"temp_slope_c_per_min":0.004,"health_state":"OK","health_score":100,"sample_count":12,"fog_node":"fog-l2"}'
PAYLOAD='{"msg_type":"telemetry_1min","id":"CS-02|2026-10-11T10:31:00Z","payload":'${INNER}'}'
DATA_B64=$(echo -n "$PAYLOAD" | base64 -w0)
ENVELOPE='{"message":{"data":"'${DATA_B64}'","attributes":{"msg_type":"telemetry_1min","unit_id":"CS-02"}},"subscription":"test"}'

RES1=$(curl -sf -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "${ENVELOPE}" \
  "${URL}/pubsub")
echo "Result: $RES1"

# 3. Duplicate (idempotency check)
echo ""
echo "[3] Send duplicate (idempotency)..."
RES2=$(curl -sf -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "${ENVELOPE}" \
  "${URL}/pubsub")
echo "Result: $RES2"

# 4. Malformed (should ack without crash)
echo ""
echo "[4] Send malformed message..."
BAD='{"message":{"data":"bm90anNvbg==","attributes":{}},"subscription":"test"}'
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "$BAD" \
  "${URL}/pubsub")
echo "HTTP status: $STATUS (expected 200 or 204)"

# 5. Check BigQuery row landed
echo ""
echo "[5] Checking BigQuery for test row (waiting 5s)..."
sleep 5
bq query --use_legacy_sql=false \
  "SELECT COUNT(*) as cnt FROM \`coldstorage.v_telemetry_dedup\` WHERE unit_id='CS-02' AND source='live'"

echo ""
echo "=== GATE G4a complete ==="
