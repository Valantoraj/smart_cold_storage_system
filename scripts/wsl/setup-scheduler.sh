#!/usr/bin/env bash
set -euo pipefail
cp -r /mnt/c/Users/valan/AppData/Roaming/gcloud/. ~/.config/gcloud/ 2>/dev/null || true

PROJECT="project-f47e3be0-07f0-4225-b8e"
REGION="us-central1"
AGENT_URL="https://maintenance-agent-qkttklqguq-uc.a.run.app"
INVOKER_SA="invoker-sa@${PROJECT}.iam.gserviceaccount.com"

echo "=== [1] Enabling Cloud Scheduler API ==="
gcloud services enable cloudscheduler.googleapis.com \
  --project="${PROJECT}" --quiet 2>&1 | tail -1
echo "  + done"

echo ""
echo "=== [2] Creating agent-cycle job (every 5 min) ==="
gcloud scheduler jobs create http agent-cycle \
  --location="${REGION}" \
  --schedule="*/5 * * * *" \
  --uri="${AGENT_URL}/run-cycle" \
  --http-method=POST \
  --oidc-service-account-email="${INVOKER_SA}" \
  --oidc-token-audience="${AGENT_URL}" \
  --attempt-deadline=300s \
  --project="${PROJECT}" \
  --quiet 2>&1 \
  && echo "  + agent-cycle created" \
  || echo "  agent-cycle: already exists (ok)"

echo ""
echo "=== [3] Creating agent-retrain job (every 6h) ==="
gcloud scheduler jobs create http agent-retrain \
  --location="${REGION}" \
  --schedule="0 */6 * * *" \
  --uri="${AGENT_URL}/admin/retrain" \
  --http-method=POST \
  --oidc-service-account-email="${INVOKER_SA}" \
  --oidc-token-audience="${AGENT_URL}" \
  --attempt-deadline=60s \
  --project="${PROJECT}" \
  --quiet 2>&1 \
  && echo "  + agent-retrain created" \
  || echo "  agent-retrain: already exists (ok)"

echo ""
echo "=== [4] Listing scheduler jobs ==="
gcloud scheduler jobs list \
  --location="${REGION}" \
  --project="${PROJECT}" \
  --format="table(name.basename(),schedule,state)" 2>&1
