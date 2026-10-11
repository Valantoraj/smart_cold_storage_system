#!/usr/bin/env bash
set -e
cp -r /mnt/c/Users/valan/AppData/Roaming/gcloud/. ~/.config/gcloud/ 2>/dev/null || true

PROJECT="project-f47e3be0-07f0-4225-b8e"
TOKEN=$(gcloud auth application-default print-access-token 2>/dev/null)

echo "=== Testing gemini-3.5-flash at location: global ==="
RESPONSE=$(curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  "https://aiplatform.googleapis.com/v1/projects/${PROJECT}/locations/global/publishers/google/models/gemini-3.5-flash:generateContent" \
  -d '{"contents":[{"role":"user","parts":[{"text":"Reply with exactly: GEMINI_OK"}]}]}')

echo "$RESPONSE" | python3 -c "
import sys, json
d = json.load(sys.stdin)
if 'error' in d:
    print('FAIL:', d['error'].get('message','unknown'))
else:
    text = d['candidates'][0]['content']['parts'][0]['text']
    print('VERIFIED: gemini-3.5-flash at global')
    print('Response:', text.strip()[:80])
"
