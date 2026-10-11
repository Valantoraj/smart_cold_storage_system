#!/usr/bin/env bash
# Gate G5b — InfluxDB + Grafana running on L2
set -euo pipefail

source ~/cold-twin/config/topology.env 2>/dev/null || true
L2_IP="${L2_IP:-localhost}"

PASS=0; FAIL=0
check() { local label="$1" result="$2"
    if [ "$result" = "PASS" ]; then echo "  [PASS] $label"; PASS=$((PASS+1))
    else echo "  [FAIL] $label — $result"; FAIL=$((FAIL+1)); fi
}

echo "=== [1] InfluxDB health ==="
CODE=$(wget -qO- --server-response "http://${L2_IP}:8086/health" 2>&1 | grep "HTTP/" | tail -1 | awk '{print $2}')
BODY=$(wget -qO- "http://${L2_IP}:8086/health" 2>/dev/null)
echo "  HTTP: $CODE  Body: $BODY"
[ "$CODE" = "200" ] && echo "$BODY" | grep -q '"pass"\|"status":"pass"' \
    && check "InfluxDB /health returns pass" "PASS" \
    || check "InfluxDB health (code=$CODE)" "FAIL"

echo ""
echo "=== [2] Grafana health ==="
GCODE=$(wget -qO- --server-response "http://${L2_IP}:3000/api/health" 2>&1 | grep "HTTP/" | tail -1 | awk '{print $2}')
GBODY=$(wget -qO- "http://${L2_IP}:3000/api/health" 2>/dev/null)
echo "  HTTP: $GCODE  Body: ${GBODY:0:80}"
[ "$GCODE" = "200" ] \
    && check "Grafana /api/health returns 200" "PASS" \
    || check "Grafana health (code=$GCODE)" "FAIL"

echo ""
echo "========================================"
echo "GATE G5b: PASS=${PASS} FAIL=${FAIL}"
[ "$FAIL" -eq 0 ] && echo "STATUS: PASS" || echo "STATUS: FAIL"
echo "========================================"
