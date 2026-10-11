#!/usr/bin/env bash
cp -r /mnt/c/Users/valan/AppData/Roaming/gcloud/. ~/.config/gcloud/ 2>/dev/null || true
URL="https://ingest-service-qkttklqguq-uc.a.run.app"

# Generate identity token with correct audience
TOKEN=$(gcloud auth print-identity-token --audiences="${URL}")
echo "URL: $URL"
HTTP=$(curl -s -o /tmp/resp.txt -w "%{http_code}" \
  -H "Authorization: Bearer ${TOKEN}" \
  "${URL}/healthz")
echo "HTTP: $HTTP"
cat /tmp/resp.txt
echo ""
