#!/usr/bin/env bash
# deploy-maintenance-agent.sh
# Builds, pushes, and deploys the maintenance-agent to Cloud Run.
set -euo pipefail

cp -r /mnt/c/Users/valan/AppData/Roaming/gcloud/. ~/.config/gcloud/ 2>/dev/null || true

PROJECT="project-f47e3be0-07f0-4225-b8e"
REGION="us-central1"
REPO="us-central1-docker.pkg.dev/${PROJECT}/coldtwin"
IMAGE="${REPO}/maintenance-agent:1.0.0"
SVC_DIR="$HOME/cold-twin/cloud/maintenance-agent"

echo "=== [1/5] Preparing build context ==="
# Copy config files into the build context
mkdir -p "${SVC_DIR}/config"
cp "$HOME/cold-twin/config/rules.json" "${SVC_DIR}/config/"
cp "$HOME/cold-twin/config/units.json" "${SVC_DIR}/config/"
echo "  + config files copied"

echo ""
echo "=== [2/5] Building Docker image ==="
docker build -t "${IMAGE}" "${SVC_DIR}"
echo "  + build done"

echo ""
echo "=== [3/5] Pushing to Artifact Registry ==="
gcloud auth configure-docker us-central1-docker.pkg.dev --quiet
docker push "${IMAGE}"
echo "  + push done"

echo ""
echo "=== [4/5] Deploying to Cloud Run ==="
gcloud run deploy maintenance-agent \
  --image="${IMAGE}" \
  --region="${REGION}" \
  --project="${PROJECT}" \
  --service-account="agent-sa@${PROJECT}.iam.gserviceaccount.com" \
  --no-allow-unauthenticated \
  --timeout=300 \
  --memory=512Mi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=3 \
  --set-env-vars="GCP_PROJECT_ID=${PROJECT},BQ_DATASET=coldstorage,GEMINI_MODEL=gemini-3.5-flash,GEMINI_LOCATION=global,WINDOW_MIN=30" \
  --quiet
echo "  + deploy done"

echo ""
echo "=== [5/5] Getting service URL ==="
URL=$(gcloud run services describe maintenance-agent \
  --region="${REGION}" \
  --project="${PROJECT}" \
  --format="value(status.url)")
echo "  + URL: ${URL}"
echo ""
echo "MAINTENANCE_AGENT_URL=${URL}"
echo "${URL}" > /tmp/maintenance-agent-url.txt

echo ""
echo "=== Deploy complete ==="
echo "  Image:   ${IMAGE}"
echo "  Service: ${URL}"
