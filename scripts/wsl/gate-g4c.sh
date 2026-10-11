#!/usr/bin/env bash
# gate-g4c.sh — Gate G4c: maintenance-agent smoke test
set -euo pipefail
cp -r /mnt/c/Users/valan/AppData/Roaming/gcloud/. ~/.config/gcloud/ 2>/dev/null || true

PROJECT="project-f47e3be0-07f0-4225-b8e"
AGENT_URL="https://maintenance-agent-qkttklqguq-uc.a.run.app"
INVOKER_SA="invoker-sa@${PROJECT}.iam.gserviceaccount.com"

PASS=0
FAIL=0

check() {
    local label="$1"
    local result="$2"
    if [ "$result" = "PASS" ]; then
        echo "  [PASS] $label"
        PASS=$((PASS+1))
    else
        echo "  [FAIL] $label — $result"
        FAIL=$((FAIL+1))
    fi
}

# Get OIDC token — use current user's identity token (ADC account has invoker role)
echo "=== Getting identity token ==="
TOKEN=$(gcloud auth print-identity-token --audiences="${AGENT_URL}" 2>/dev/null) \
  || TOKEN=$(gcloud auth print-identity-token 2>/dev/null)
echo "  + token obtained"

echo ""
echo "=== [1] Health check ==="
HEALTH=$(curl -s -o /tmp/g4c_health.json -w "%{http_code}" \
  -H "Authorization: Bearer ${TOKEN}" \
  "${AGENT_URL}/healthz")
cat /tmp/g4c_health.json
echo ""
if [ "$HEALTH" = "200" ]; then
    check "healthz returns 200" "PASS"
    MODEL=$(python3 -c "import json; d=json.load(open('/tmp/g4c_health.json')); print(d.get('model','?'))")
    check "model field present: ${MODEL}" "PASS"
else
    check "healthz returns 200 (got ${HEALTH})" "FAIL: HTTP ${HEALTH}"
fi

echo ""
echo "=== [2] Dry-run cycle ==="
DRY=$(curl -s -o /tmp/g4c_dry.json -w "%{http_code}" \
  -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  "${AGENT_URL}/run-cycle?dry_run=true")
echo "HTTP: $DRY"

if [ "$DRY" = "200" ]; then
    check "dry-run returns 200" "PASS"
    python3 - <<'PYEOF'
import json, sys
try:
    d = json.load(open('/tmp/g4c_dry.json'))
    run_id = d.get('run_id','')
    units  = d.get('units_evaluated', 0)
    decs   = d.get('decisions', [])
    llm_f  = d.get('llm_failed', None)
    model  = d.get('model_used', '?')
    print(f"  run_id:          {run_id}")
    print(f"  units_evaluated: {units}")
    print(f"  decisions count: {len(decs)}")
    print(f"  llm_failed:      {llm_f}")
    print(f"  model_used:      {model}")
    for dec in decs:
        uid = dec.get('unit_id','?')
        act = dec.get('action','?')
        urg = dec.get('urgency','?')
        src = dec.get('source','?')
        print(f"    {uid}: action={act} urgency={urg} source={src}")
    if run_id:
        print("CHECK_RUN_ID: PASS")
    if units == 3:
        print("CHECK_UNITS_3: PASS")
    if len(decs) >= 3:
        print("CHECK_DECISIONS: PASS")
except Exception as e:
    print(f"PARSE_ERROR: {e}")
    sys.exit(1)
PYEOF
else
    check "dry-run returns 200 (got ${DRY})" "FAIL: HTTP ${DRY}"
    cat /tmp/g4c_dry.json
fi

echo ""
echo "=== [3] Real run (async) ==="
REAL=$(curl -s -o /tmp/g4c_real.json -w "%{http_code}" \
  -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  "${AGENT_URL}/run-cycle")
cat /tmp/g4c_real.json
echo ""
if [ "$REAL" = "202" ]; then
    check "real run returns 202 Accepted" "PASS"
    REAL_RUN_ID=$(python3 -c "import json; print(json.load(open('/tmp/g4c_real.json')).get('run_id',''))")
    echo "  real run_id: ${REAL_RUN_ID}"
else
    check "real run returns 202 Accepted (got ${REAL})" "FAIL: HTTP ${REAL}"
fi

echo ""
echo "=== [4] Waiting 30s for async run to complete ==="
sleep 30

echo ""
echo "=== [5] Verify agent_runs row in BigQuery ==="
/tmp/gemini-venv/bin/python3 - <<'PYEOF'
from google.cloud import bigquery
import sys

bq = bigquery.Client(project="project-f47e3be0-07f0-4225-b8e")
rows = list(bq.query("""
    SELECT run_id, started_at, completed_at, trigger, llm_failed, model_used
    FROM `project-f47e3be0-07f0-4225-b8e.coldstorage.agent_runs`
    ORDER BY started_at DESC
    LIMIT 3
""").result())

if not rows:
    print("CHECK_BQ_ROW: FAIL — no rows in agent_runs")
    sys.exit(1)

print(f"CHECK_BQ_ROW: PASS — {len(rows)} row(s) found")
for r in rows:
    print(f"  run_id={r['run_id']}  trigger={r['trigger']}  "
          f"llm_failed={r['llm_failed']}  model={r['model_used']}")
PYEOF

echo ""
echo "=== [6] Check /last-run endpoint ==="
LAST=$(curl -s -o /tmp/g4c_last.json -w "%{http_code}" \
  -H "Authorization: Bearer ${TOKEN}" \
  "${AGENT_URL}/last-run")
if [ "$LAST" = "200" ]; then
    check "last-run returns 200" "PASS"
    python3 -c "
import json
d = json.load(open('/tmp/g4c_last.json'))
print(f\"  run_id: {d.get('run_id','?')}\")
print(f\"  trigger: {d.get('trigger','?')}\")
print(f\"  model_used: {d.get('model_used','?')}\")
"
else
    check "last-run returns 200 (got ${LAST})" "FAIL: HTTP ${LAST}"
fi

echo ""
echo "========================================"
echo "GATE G4c SUMMARY"
echo "  PASS: ${PASS}   FAIL: ${FAIL}"
if [ "$FAIL" -eq 0 ]; then
    echo "  STATUS: PASS"
else
    echo "  STATUS: FAIL"
fi
echo "========================================"
