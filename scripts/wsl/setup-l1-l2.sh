#!/usr/bin/env bash
# Run from L3 to set up L1 and L2 remotely
set -e

KEY=~/.ssh/id_ed25519
TOKEN="GH_TOKEN_REPLACE_ME"
REPO="https://${TOKEN}@github.com/Valantoraj/smart_cold_storage_system.git"

ssh_l1() { ssh -p 2222 -i $KEY -o StrictHostKeyChecking=no -o ConnectTimeout=15 nithish@100.74.249.115 "$@"; }
ssh_l2() { ssh -p 2222 -i $KEY -o StrictHostKeyChecking=no -o ConnectTimeout=15 roop@100.83.223.86 "$@"; }

echo "================================================="
echo "  Remote Setup: L1 and L2"
echo "================================================="

# ── L1: clone repo ────────────────────────────────────────────────────────
echo ""
echo "=== L1: Clone repo ==="
ssh_l1 "rm -rf ~/cold-twin && git clone -b cold-twin ${REPO} ~/cold-twin && echo L1_CLONE_OK"

echo "=== L1: topology.env ==="
ssh_l1 "cd ~/cold-twin && cp config/topology.env.example config/topology.env"
# Push L3's topology.env values to L1
scp -P 2222 -i $KEY -o StrictHostKeyChecking=no ~/cold-twin/config/topology.env nithish@100.74.249.115:~/cold-twin/config/topology.env
ssh_l1 "echo L1_ROLE=edge >> ~/cold-twin/config/topology.env && grep L1_IP ~/cold-twin/config/topology.env"

echo "=== L1: Install Docker Engine ==="
ssh_l1 "command -v docker &>/dev/null && echo 'Docker already installed' || (curl -fsSL https://get.docker.com | sudo sh && sudo usermod -aG docker nithish)"

echo "=== L1: Install gcloud ==="
ssh_l1 "command -v gcloud &>/dev/null && echo 'gcloud already installed' || (curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg && echo 'deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main' | sudo tee /etc/apt/sources.list.d/google-cloud-sdk.list && sudo apt-get update -qq && sudo apt-get install -y -qq google-cloud-cli)"

echo "=== L1: Run prep-host.sh ==="
ssh_l1 "cd ~/cold-twin && ROLE=edge bash scripts/wsl/prep-host.sh 2>&1 | tail -5"

echo ""
echo "=== L2: Clone repo ==="
ssh_l2 "rm -rf ~/cold-twin && git clone -b cold-twin ${REPO} ~/cold-twin && echo L2_CLONE_OK"

echo "=== L2: topology.env ==="
ssh_l2 "cd ~/cold-twin && cp config/topology.env.example config/topology.env"
scp -P 2222 -i $KEY -o StrictHostKeyChecking=no ~/cold-twin/config/topology.env roop@100.83.223.86:~/cold-twin/config/topology.env
ssh_l2 "echo L2_ROLE=fog >> ~/cold-twin/config/topology.env && grep L2_IP ~/cold-twin/config/topology.env"

echo "=== L2: Install Docker Engine ==="
ssh_l2 "command -v docker &>/dev/null && echo 'Docker already installed' || (curl -fsSL https://get.docker.com | sudo sh && sudo usermod -aG docker roop)"

echo "=== L2: Install gcloud ==="
ssh_l2 "command -v gcloud &>/dev/null && echo 'gcloud already installed' || (curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg && echo 'deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main' | sudo tee /etc/apt/sources.list.d/google-cloud-sdk.list && sudo apt-get update -qq && sudo apt-get install -y -qq google-cloud-cli)"

echo "=== L2: Run prep-host.sh ==="
ssh_l2 "cd ~/cold-twin && ROLE=fog bash scripts/wsl/prep-host.sh 2>&1 | tail -5"

echo ""
echo "================================================="
echo "  L1 and L2 setup complete!"
echo "================================================="
