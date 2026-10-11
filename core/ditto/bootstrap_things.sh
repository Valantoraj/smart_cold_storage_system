#!/usr/bin/env bash
# bootstrap_things.sh
# Creates the three cold storage digital twin things in Eclipse Ditto.
# Run on L3 after 'docker compose up -d' and Ditto is healthy.
# Usage: ./bootstrap_things.sh [DITTO_HOST] [DITTO_PORT] [DITTO_USER] [DITTO_PASSWORD]

set -euo pipefail

DITTO_HOST="${1:-localhost}"
DITTO_PORT="${2:-8080}"
DITTO_USER="${3:-${DITTO_USER:-ditto}}"
DITTO_PASS="${4:-${DITTO_PASSWORD:-ditto}}"
BASE="http://${DITTO_HOST}:${DITTO_PORT}/api/2"
AUTH="${DITTO_USER}:${DITTO_PASS}"

echo "=== Bootstrapping Ditto things at ${BASE} ==="

# Wait for Ditto to be ready
echo "Waiting for Ditto gateway..."
for i in $(seq 1 30); do
    if wget -qO- "http://${DITTO_HOST}:${DITTO_PORT}/health" 2>/dev/null | grep -q ok; then
        echo "  + Ditto is ready (attempt $i)"
        break
    fi
    sleep 5
    if [ "$i" -eq 30 ]; then
        echo "ERROR: Ditto not ready after 150s"
        exit 1
    fi
done

# Create default policy
echo ""
echo "Creating default policy..."
wget -qO- --method=PUT \
    --header="Content-Type: application/json" \
    --header="Authorization: Basic $(echo -n "${AUTH}" | base64)" \
    --body-data='{
  "entries": {
    "DEFAULT": {
      "subjects": {
        "nginx:ditto": {"type": "pre-authenticated"}
      },
      "resources": {
        "thing:/": {"grant": ["READ","WRITE"], "revoke": []},
        "policy:/": {"grant": ["READ","WRITE"], "revoke": []},
        "message:/": {"grant": ["READ","WRITE"], "revoke": []}
      }
    }
  }
}' \
    "${BASE}/policies/coldstorage:default-policy" 2>&1 || true
echo "  + policy done"

# Create each thing
for UNIT in CS-01 CS-02 CS-03; do
    THING_ID="coldstorage:${UNIT}"

    case "$UNIT" in
      CS-01) SETPOINT=4.0; HARD_LIMIT=8.0; HUM_LO=55; HUM_HI=85 ;;
      CS-02) SETPOINT=4.0; HARD_LIMIT=8.0; HUM_LO=55; HUM_HI=85 ;;
      CS-03) SETPOINT=5.0; HARD_LIMIT=8.0; HUM_LO=55; HUM_HI=85 ;;
    esac

    echo ""
    echo "Creating thing: ${THING_ID} ..."
    wget -qO- --method=PUT \
        --header="Content-Type: application/json" \
        --header="Authorization: Basic $(echo -n "${AUTH}" | base64)" \
        --body-data="{
  \"policyId\": \"coldstorage:default-policy\",
  \"attributes\": {
    \"setpoint_c\": ${SETPOINT},
    \"hard_limit_c\": ${HARD_LIMIT},
    \"humidity_range\": [${HUM_LO}, ${HUM_HI}],
    \"unit_id\": \"${UNIT}\",
    \"location\": \"Cold Storage Facility\"
  },
  \"features\": {
    \"environment\": {\"properties\": {\"temperature_c\": null, \"humidity_pct\": null}},
    \"compressor\":  {\"properties\": {\"status\": \"unknown\", \"duty_15m\": null}},
    \"energy\":      {\"properties\": {\"power_kw\": null, \"on_power_kw\": null}},
    \"health\":      {\"properties\": {\"state\": \"OK\", \"score\": 100, \"reasons\": []}},
    \"advice\":      {\"properties\": {\"action\": null, \"urgency\": null, \"message\": null, \"work_order_id\": null, \"received_at\": null}},
    \"meta\":        {\"properties\": {\"last_update\": null, \"edge_node\": null, \"fog_node\": null}}
  }
}" \
        "${BASE}/things/${THING_ID}" 2>&1 | tail -1
    echo "  + ${THING_ID} created"
done

echo ""
echo "=== Bootstrap complete. Verifying ==="
for UNIT in CS-01 CS-02 CS-03; do
    RESULT=$(wget -qO- \
        --header="Authorization: Basic $(echo -n "${AUTH}" | base64)" \
        "${BASE}/things/coldstorage:${UNIT}" 2>/dev/null | \
        grep -o '"thingId":"[^"]*"' | head -1)
    echo "  ${UNIT}: ${RESULT}"
done
echo ""
echo "Done. Access Ditto at http://${DITTO_HOST}:${DITTO_PORT}/api/2/things"
