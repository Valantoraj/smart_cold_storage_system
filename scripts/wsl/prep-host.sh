#!/usr/bin/env bash
# prep-host.sh — idempotent setup script for L1, L2, L3
# Works on Ubuntu 22.04 and 24.04
# Run as: bash prep-host.sh
set -e

ROLE="${ROLE:-unknown}"  # set via: ROLE=edge bash prep-host.sh
echo "=== prep-host.sh starting (role=${ROLE}) ==="

# ── 1. Packages ────────────────────────────────────────────────────────────
echo "[1/6] Installing packages..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
  curl wget git jq netcat-openbsd mosquitto-clients \
  python3-pip python3-venv python3-full unzip ca-certificates \
  openssh-server iproute2 iptables

# ── 2. Docker Engine ───────────────────────────────────────────────────────
echo "[2/6] Docker Engine..."
if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
  echo "  Docker already running"
else
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
fi
sudo systemctl enable docker
sudo systemctl start docker
# Apply group without re-login
if ! docker info &>/dev/null 2>&1; then
  sudo docker run --rm hello-world 2>&1 | grep "Hello from Docker" || true
else
  docker run --rm hello-world 2>&1 | grep "Hello from Docker"
fi
echo "  Docker OK"

# ── 3. SSH on port 2222 ────────────────────────────────────────────────────
echo "[3/6] SSH on port 2222..."
sudo mkdir -p /etc/ssh/sshd_config.d
sudo tee /etc/ssh/sshd_config.d/coldtwin.conf > /dev/null <<'SSHEOF'
Port 2222
PasswordAuthentication no
PubkeyAuthentication yes
SSHEOF

# Ubuntu 24.04 uses socket activation — must disable it first
UBUNTU_VER=$(lsb_release -sr 2>/dev/null || echo "22.04")
if [[ "$UBUNTU_VER" == 24* ]]; then
  sudo systemctl disable --now ssh.socket 2>/dev/null || true
fi
sudo systemctl enable ssh
sudo systemctl start ssh
sleep 2
if ss -tlnp | grep -q ':2222'; then
  echo "  SSH listening on 2222 OK"
else
  echo "  WARNING: SSH not on 2222 — checking port 22"
  ss -tlnp | grep ':22' || echo "  SSH not running at all"
fi

# ── 4. Passwordless sudo ───────────────────────────────────────────────────
echo "[4/6] Passwordless sudo..."
echo "$USER ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/"$USER" > /dev/null
sudo chmod 440 /etc/sudoers.d/"$USER"
echo "  OK"

# ── 5. SSH key pair ────────────────────────────────────────────────────────
echo "[5/6] SSH key..."
mkdir -p ~/.ssh && chmod 700 ~/.ssh
if [ ! -f ~/.ssh/id_ed25519 ]; then
  ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N "" -q
  echo "  Key generated"
else
  echo "  Key already exists"
fi
# Self-authorize
cat ~/.ssh/id_ed25519.pub >> ~/.ssh/authorized_keys
sort -u ~/.ssh/authorized_keys -o ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
echo "  Public key:"
cat ~/.ssh/id_ed25519.pub

# ── 6. Network info ────────────────────────────────────────────────────────
echo "[6/6] Network info..."
TAILSCALE_IP=$(tailscale ip -4 2>/dev/null || /snap/bin/tailscale ip -4 2>/dev/null || echo "tailscale-not-installed")
LAN_IP=$(ip route get 1.1.1.1 2>/dev/null | grep -oP 'src \K[\d.]+' | head -1 || hostname -I | awk '{print $1}')
echo "  LAN IP      : ${LAN_IP}"
echo "  Tailscale IP: ${TAILSCALE_IP}"
echo "  Linux user  : $USER"
echo "  Ubuntu ver  : $(lsb_release -sr)"
echo "  Role        : ${ROLE}"
echo ""
echo "=== Add to topology.env ==="
echo "  LINUX_USER=${USER}"
if [[ "$ROLE" == "edge" ]]; then
  echo "  L1_IP=${TAILSCALE_IP}   # Tailscale IP of L1 (edge)"
elif [[ "$ROLE" == "fog" ]]; then
  echo "  L2_IP=${TAILSCALE_IP}   # Tailscale IP of L2 (fog)"
else
  echo "  L3_IP=${TAILSCALE_IP}   # Tailscale IP of L3 (control/core)"
fi
echo ""
echo "=== prep-host.sh COMPLETE ==="
