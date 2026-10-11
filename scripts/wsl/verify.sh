#!/usr/bin/env bash
KEY=~/.ssh/id_ed25519

echo "=== L1 ==="
ssh -p 2222 -i $KEY -o StrictHostKeyChecking=no -o ConnectTimeout=10 nithish@100.74.249.115 \
  'echo "user=$(whoami) host=$(hostname)" && ls ~/cold-twin/config/ && docker --version && gcloud --version 2>&1 | head -1' 2>&1

echo ""
echo "=== L2 ==="
ssh -p 2222 -i $KEY -o StrictHostKeyChecking=no -o ConnectTimeout=10 roop@100.83.223.86 \
  'echo "user=$(whoami) host=$(hostname)" && ls ~/cold-twin/config/ && docker --version && gcloud --version 2>&1 | head -1' 2>&1

echo ""
echo "=== ALL DONE ==="
