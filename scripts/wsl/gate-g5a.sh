#!/usr/bin/env bash
# Gate G5a — Ditto running on L3, accessible from local host
set -euo pipefail
cp -r /mnt/c/Users/valan/AppData/Roaming/gcloud/. ~/.config/gcloud/ 2>/dev/null || true

source ~/cold-twin/config/topology.env 2>/dev/null || true
L3_IP="${L3_IP:-localhost}"
DITTO_USER="${DITTO_USER:-ditto}"
DITTO_PASS="${DITTO_PASSWORD:-ditto}"
BASE="http://${L3_IP}:8080/api/2"
AUTH=$(echo -n "${DITTO_USER}:${DITTO_PASS}" | base64)

PASS=0; FAIL=0
check() { local label="$1" result="$2"
    if [ "$result" = "PASS" ]; then echo "  [PASS] $label"; PASS=$((PASS+1))
    else echo "  [FAIL] $label — $result"; FAIL=$((FAIL+1)); fi
}

echo "=== [1] Ditto health check ==="
CODE=$(wget -qO- --server-response "http://${L3_IP}:8080/health" 2>&1 | grep "HTTP/" | tail -1 | awk '{print $2}')
[ "$CODE" = "200" ] && check "Ditto /health returns 200" "PASS" || check "Ditto /health (got $CODE)" "FAIL"

echo ""
echo "=== [2] GET CS-01 thing ==="
RESULT=$(wget -qO- \
    --header="Authorization: Basic ${AUTH}" \
    "${BASE}/things/coldstorage:CS-01" 2>/dev/null)
echo "$RESULT" | grep -q '"thingId"' \
    && check "GET CS-01 returns thingId" "PASS" \
    || check "GET CS-01 no thingId in response" "FAIL: ${RESULT:0:100}"

echo ""
echo "=== [3] PATCH temperature on CS-01 ==="
wget -qO- --method=PATCH \
    --header="Content-Type: application/merge-patch+json" \
    --header="Authorization: Basic ${AUTH}" \
    --body-data='{"features":{"environment":{"properties":{"temperature_c":4.2}}}}' \
    "${BASE}/things/coldstorage:CS-01" > /tmp/g5a_patch.out 2>&1
PATCH_CODE=$?
[ "$PATCH_CODE" -eq 0 ] && check "PATCH CS-01 temperature succeeds" "PASS" \
    || check "PATCH failed" "FAIL"

echo ""
echo "=== [4] Verify PATCH was applied ==="
TEMP=$(wget -qO- \
    --header="Authorization: Basic ${AUTH}" \
    "${BASE}/things/coldstorage:CS-01/features/environment/properties/temperature_c" 2>/dev/null)
echo "  temperature_c = $TEMP"
echo "$TEMP" | grep -q "4.2" \
    && check "temperature_c == 4.2 after PATCH" "PASS" \
    || check "temperature_c not 4.2 (got: $TEMP)" "FAIL"

echo ""
echo "========================================"
echo "GATE G5a: PASS=${PASS} FAIL=${FAIL}"
[ "$FAIL" -eq 0 ] && echo "STATUS: PASS" || echo "STATUS: FAIL"
echo "========================================"
