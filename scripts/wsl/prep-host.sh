#!/usr/bin/env bash
# prep-host.sh — idempotent L3 setup script
# Run as: bash scripts/wsl/prep-host.sh
set -e

echo "=== [1/6] Update packages ==="
sudo apt-get update -qq
sudo apt-get install -y -qq \
  curl wget git jq netcat-openbsd mosquitto-clients \
  python3-pip python3-venv unzip ca-certificates \
  openssh-server iproute2

echo "=== [2/6] Docker Engine (skip if already installed) ==="
if ! command -v docker &>/dev/null; then
  curl -fsSL https://get.docker.com | sudo sh
fi
sudo usermod -aG docker "$USER"
sudo systemctl enable docker
sudo systemctl start docker
docker run --rm hello-world 2>&1 | grep "Hello from Docker"

echo "=== [3/6] SSH on port 2222 ==="
sudo mkdir -p /etc/ssh/sshd_config.d
sudo tee /etc/ssh/sshd_config.d/coldtwin.conf > /dev/null <<'EOF'
Port 2222
PasswordAuthentication no
PubkeyAuthentication yes
EOF
# Ubuntu 24.04: disable socket activation
sudo systemctl disable --now ssh.socket 2>/dev/null || true
sudo systemctl enable ssh
sudo systemctl start ssh
sleep 2
if ss -tlnp | grep -q ':2222'; then
  echo "SSH listening on port 2222 OK"
else
  echo "WARNING: SSH not on port 2222, checking default port"
  ss -tlnp | grep ':22' || echo "SSH not running at all"
fi

echo "=== [4/6] Passwordless sudo ==="
echo "$USER ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/"$USER" > /dev/null
sudo chmod 440 /etc/sudoers.d/"$USER"
echo "Passwordless sudo configured"

echo "=== [5/6] SSH key pair ==="
mkdir -p ~/.ssh && chmod 700 ~/.ssh
if [ ! -f ~/.ssh/id_ed25519 ]; then
  ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N "" -q
  echo "SSH key generated"
else
  echo "SSH key already exists"
fi
# Self-authorize (L3 SSH to itself for iofogctl)
cat ~/.ssh/id_ed25519.pub >> ~/.ssh/authorized_keys
sort -u ~/.ssh/authorized_keys -o ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys

echo "=== [6/6] Network info ==="
L3_IP=$(ip route get 1.1.1.1 2>/dev/null | grep -oP 'src \K[\d.]+' | head -1 || hostname -I | awk '{print $1}')
echo "L3_IP=${L3_IP}"
echo "Add this to config/topology.env: L3_IP=${L3_IP}"
echo "Linux user: $USER"
echo ""
echo "=== prep-host.sh COMPLETE ==="
