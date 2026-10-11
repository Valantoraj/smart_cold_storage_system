#!/usr/bin/env bash
cp -r /mnt/c/Users/valan/AppData/Roaming/gcloud/. ~/.config/gcloud/ 2>/dev/null || true

AGENT_URL="https://maintenance-agent-qkttklqguq-uc.a.run.app"
TOKEN=$(gcloud auth print-identity-token 2>/dev/null)

echo "=== Testing all endpoints ==="
for PATH in "/healthz" "/run-cycle?dry_run=true" "/last-run"; do
    if [ "$PATH" = "/run-cycle?dry_run=true" ]; then
        CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
          -H "Authorization: Bearer ${TOKEN}" "${AGENT_URL}${PATH}")
    else
        CODE=$(curl -s -o /dev/null -w "%{http_code}" \
          -H "Authorization: Bearer ${TOKEN}" "${AGENT_URL}${PATH}")
    fi
    echo "  ${PATH} -> HTTP ${CODE}"
done

echo ""
echo "=== Healthz response body ==="
curl -s -H "Authorization: Bearer ${TOKEN}" "${AGENT_URL}/healthz"
echo ""
