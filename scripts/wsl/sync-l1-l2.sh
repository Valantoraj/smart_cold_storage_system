#!/usr/bin/env bash
# Sync latest cold-twin-clean branch to L1 and L2
KEY=~/.ssh/id_ed25519
# TOKEN is read from environment or ~/.netrc — do NOT hard-code here
REPO="https://github.com/Valantoraj/smart_cold_storage_system.git"

ssh_l1() { ssh -p 2222 -i $KEY -o StrictHostKeyChecking=no -o ConnectTimeout=15 nithish@100.74.249.115 "$@"; }
ssh_l2() { ssh -p 2222 -i $KEY -o StrictHostKeyChecking=no -o ConnectTimeout=15 roop@100.83.223.86 "$@"; }

echo "=== Syncing L1 ==="
ssh_l1 "cd ~/cold-twin && git fetch origin && git checkout cold-twin-clean 2>/dev/null || (git remote set-url origin ${REPO} && git fetch origin && git checkout -b cold-twin-clean origin/cold-twin-clean 2>/dev/null || git reset --hard origin/cold-twin-clean) && echo L1_SYNC_OK" 2>&1

echo ""
echo "=== Syncing L2 ==="
ssh_l2 "cd ~/cold-twin && git fetch origin && git checkout cold-twin-clean 2>/dev/null || (git remote set-url origin ${REPO} && git fetch origin && git checkout -b cold-twin-clean origin/cold-twin-clean 2>/dev/null || git reset --hard origin/cold-twin-clean) && echo L2_SYNC_OK" 2>&1

echo ""
echo "=== Done ==="
