#!/bin/bash
# =============================================================================
# GCP Central Services Setup — Smart Cold Storage Digital Twin
# =============================================================================
# Run on the GCP e2-micro VM after gcp/setup.sh creates it.
# Installs: Central InfluxDB, Eclipse Ditto (optional), Grafana
#
# SSH into the VM first:
#   gcloud compute ssh iofog-controller --zone=asia-south1-a
# Then run:
#   curl -sSL https://raw.githubusercontent.com/your-repo/main/gcp/central-services.sh | bash
# Or copy this file and run locally on the VM.
# =============================================================================

set -e

echo "========================================================"
echo "  GCP Central Services — InfluxDB + Ditto + Grafana"
echo "========================================================"

# ─── Docker + Docker Compose ─────────────────────────────────────────────────
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    apt-get update -qq
    apt-get install -y -qq docker.io docker-compose-v2 curl wget
    systemctl enable docker
    systemctl start docker
fi

# ─── Create Central InfluxDB ─────────────────────────────────────────────────
mkdir -p /opt/smart-cooling/central-influxdb
cat > /opt/smart-cooling/central-influxdb/docker-compose.yml << 'EOF'
version: '3.8'
services:
  central-influxdb:
    image: influxdb:2.7
    container_name: central_influxdb
    ports:
      - "8087:8086"
    environment:
      - DOCKER_INFLUXDB_INIT_MODE=setup
      - DOCKER_INFLUXDB_INIT_USERNAME=admin
      - DOCKER_INFLUXDB_INIT_PASSWORD=adminpass123
      - DOCKER_INFLUXDB_INIT_ORG=smart_cooling
      - DOCKER_INFLUXDB_INIT_BUCKET=cold_storage
      - DOCKER_INFLUXDB_INIT_RETENTION=90d
      - DOCKER_INFLUXDB_INIT_ADMIN_TOKEN=smart-cooling-super-secret-token
    volumes:
      - central_influxdb_data:/var/lib/influxdb2
      - central_influxdb_config:/etc/influxdb2
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "influx", "ping"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  central_influxdb_data:
  central_influxdb_config:
EOF

cd /opt/smart-cooling/central-influxdb
docker compose up -d
echo "✓ Central InfluxDB started on port 8087 (mapped to 8086 internally)"

# ─── Create additional buckets ────────────────────────────────────────────────
sleep 15
docker exec central_influxdb influx bucket create \
  --name alerts --org smart_cooling --retention 365d \
  --token smart-cooling-super-secret-token 2>/dev/null || true
docker exec central_influxdb influx bucket create \
  --name analytics --org smart_cooling --retention 730d \
  --token smart-cooling-super-secret-token 2>/dev/null || true
echo "✓ Central InfluxDB buckets created"

# ─── Install Grafana ──────────────────────────────────────────────────────────
mkdir -p /opt/smart-cooling/grafana/{data,provisioning/datasources,provisioning/dashboards,dashboards}

# Copy Grafana provisioning from repo (if present)
if [ -f /opt/smart-cooling/repo/grafana/provisioning ]; then
    cp -r /opt/smart-cooling/repo/grafana/provisioning/* /opt/smart-cooling/grafana/provisioning/
    cp -r /opt/smart-cooling/repo/grafana/dashboards/* /opt/smart-cooling/grafana/dashboards/
fi

cat > /opt/smart-cooling/grafana/datasources.yml << 'EOF'
apiVersion: 1
datasources:
  - name: Central InfluxDB
    type: influxdb
    access: proxy
    url: http://central_influxdb:8086
    jsonData:
      version: Flux
      organization: smart_cooling
      defaultBucket: cold_storage
      tlsSkipVerify: true
    secureJsonData:
      token: smart-cooling-super-secret-token
    editable: true
    isDefault: true

  - name: Central InfluxDB Alerts
    type: influxdb
    access: proxy
    url: http://central_influxdb:8086
    jsonData:
      version: Flux
      organization: smart_cooling
      defaultBucket: alerts
      tlsSkipVerify: true
    secureJsonData:
      token: smart-cooling-super-secret-token
    editable: true
EOF

cat > /opt/smart-cooling/grafana/docker-compose.yml << 'EOF'
version: '3.8'
services:
  grafana:
    image: grafana/grafana:10.2.0
    container_name: central_grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_USER=admin
      - GF_SECURITY_ADMIN_PASSWORD=Valan@2005
      - GF_USERS_ALLOW_SIGN_UP=false
      - GF_INSTALL_PLUGINS=grafana-bigquery-datasource
    volumes:
      - grafana_data:/var/lib/grafana
      - ./provisioning:/etc/grafana/provisioning
      - ./dashboards:/var/lib/grafana/dashboards
    networks:
      - smart_cooling_central
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3000/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3

networks:
  smart_cooling_central:
    external: true

volumes:
  grafana_data:
EOF

# Create shared network
docker network create smart_cooling_central 2>/dev/null || true

cd /opt/smart-cooling/grafana
docker compose up -d
echo "✓ Central Grafana started on port 3000"

# ─── Summary ──────────────────────────────────────────────────────────────────
VM_IP=$(hostname -I | awk '{print $1}')
echo ""
echo "========================================================"
echo "  Central Services Running!"
echo "========================================================"
echo ""
echo "  Central InfluxDB: http://${VM_IP}:8087"
echo "  Central Grafana:  http://${VM_IP}:3000 (admin / Valan@2005)"
echo ""
echo "  Edge nodes should set:"
echo "    CENTRAL_INFLUXDB_URL=http://${VM_IP}:8087"
echo "    DITTO_URL=http://${VM_IP}:8080"
echo "========================================================"
