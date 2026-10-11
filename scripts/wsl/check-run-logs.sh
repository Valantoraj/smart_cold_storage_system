#!/usr/bin/env bash
cp -r /mnt/c/Users/valan/AppData/Roaming/gcloud/. ~/.config/gcloud/ 2>/dev/null || true
echo "=== Cloud Run logs for ingest-service ==="
gcloud logging read \
  "resource.type=cloud_run_revision AND resource.labels.service_name=ingest-service" \
  --limit=20 \
  --format="table(timestamp,severity,textPayload)" \
  --project=project-f47e3be0-07f0-4225-b8e 2>&1
