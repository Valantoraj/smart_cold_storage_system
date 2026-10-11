#!/usr/bin/env bash
set -e
cp -r /mnt/c/Users/valan/AppData/Roaming/gcloud/. ~/.config/gcloud/ 2>/dev/null || true

P=project-f47e3be0-07f0-4225-b8e
INGEST_URL=https://ingest-service-405914735554.us-central1.run.app

echo "[1] Grant invoker-sa run.invoker on ingest-service..."
gcloud run services add-iam-policy-binding ingest-service \
  --region=us-central1 \
  --member="serviceAccount:invoker-sa@${P}.iam.gserviceaccount.com" \
  --role=roles/run.invoker --quiet 2>&1 | tail -2

echo "[2] Grant Pub/Sub SA token creator..."
gcloud projects add-iam-policy-binding $P \
  --member="serviceAccount:service-405914735554@gcp-sa-pubsub.iam.gserviceaccount.com" \
  --role=roles/iam.serviceAccountTokenCreator --quiet 2>&1 | tail -2

echo "[3] Create Pub/Sub push subscription..."
gcloud pubsub subscriptions create telemetry-push-sub \
  --topic=coldstorage-telemetry \
  --push-endpoint="${INGEST_URL}/pubsub" \
  --push-auth-service-account="invoker-sa@${P}.iam.gserviceaccount.com" \
  --ack-deadline=30 \
  --dead-letter-topic=telemetry-dead-letter \
  --max-delivery-attempts=5 \
  --quiet 2>&1

echo "[4] Test healthz..."
curl -sf "${INGEST_URL}/healthz" && echo " healthz OK"

echo "[5] Saving INGEST_URL to topology.env..."
grep -q INGEST_URL ~/cold-twin/config/topology.env || \
  echo "INGEST_URL=${INGEST_URL}" >> ~/cold-twin/config/topology.env

echo "GATE G4a ready — ingest-service deployed and Pub/Sub configured"
