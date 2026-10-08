#!/bin/bash
# =============================================================================
# GCP Setup Script — Smart Cold Storage Digital Twin
# =============================================================================
# Run this ONCE from Laptop 1 after creating the GCP project.
#
# Prerequisites:
#   1. Install gcloud CLI: https://cloud.google.com/sdk/docs/install
#   2. Run: gcloud auth login
#   3. Set your project: gcloud config set project <your-project-id>
#
# Usage:
#   chmod +x setup.sh
#   ./setup.sh
# =============================================================================

set -e

# ─── Load from .env ───────────────────────────────────────────────────────────
if [ -f "../.env" ]; then
  export $(grep -v '^#' ../.env | xargs)
else
  echo "ERROR: .env file not found. Copy .env.example to .env and fill in values."
  exit 1
fi

PROJECT_ID="${GCP_PROJECT_ID}"
REGION="${GCP_REGION:-asia-south1}"
DATASET="${GCP_BIGQUERY_DATASET:-cold_storage_lake}"
SA_NAME="smart-cooling-sa"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
KEY_FILE="./service-account.json"

echo "========================================================"
echo "  Smart Cold Storage — GCP Infrastructure Setup"
echo "========================================================"
echo "  Project : ${PROJECT_ID}"
echo "  Region  : ${REGION}"
echo "  Dataset : ${DATASET}"
echo "========================================================"
echo ""

# ─── Step 1: Set active project ──────────────────────────────────────────────
echo "[1/10] Setting active GCP project..."
gcloud config set project "${PROJECT_ID}"
echo "✓ Project set"

# ─── Step 2: Enable required APIs ────────────────────────────────────────────
echo "[2/10] Enabling GCP APIs (this takes ~2 minutes)..."
gcloud services enable \
  bigquery.googleapis.com \
  bigquerystorage.googleapis.com \
  aiplatform.googleapis.com \
  pubsub.googleapis.com \
  cloudscheduler.googleapis.com \
  storage.googleapis.com \
  run.googleapis.com \
  compute.googleapis.com \
  --quiet

echo "✓ APIs enabled"

# ─── Step 3: Create service account ──────────────────────────────────────────
echo "[3/10] Creating service account..."
gcloud iam service-accounts create "${SA_NAME}" \
  --display-name="Smart Cooling Service Account" \
  --quiet 2>/dev/null || echo "  (service account already exists)"

# Grant roles
ROLES=(
  "roles/bigquery.dataEditor"
  "roles/bigquery.jobUser"
  "roles/bigquery.dataViewer"
  "roles/aiplatform.user"
  "roles/pubsub.publisher"
  "roles/pubsub.subscriber"
  "roles/storage.objectAdmin"
)

echo "  Granting IAM roles..."
for ROLE in "${ROLES[@]}"; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="${ROLE}" \
    --quiet > /dev/null
done
echo "✓ Service account configured"

# ─── Step 4: Download service account key ────────────────────────────────────
echo "[4/10] Downloading service account key..."
if [ ! -f "${KEY_FILE}" ]; then
  gcloud iam service-accounts keys create "${KEY_FILE}" \
    --iam-account="${SA_EMAIL}" \
    --quiet
  echo "✓ Key saved to ${KEY_FILE}  ← KEEP THIS SECRET, never commit"
else
  echo "  (key file already exists, skipping)"
fi

# ─── Step 5: Create BigQuery dataset ─────────────────────────────────────────
echo "[5/10] Creating BigQuery dataset..."
bq --location="${REGION}" mk \
  --dataset \
  --description="Smart Cold Storage sensor data lake" \
  "${PROJECT_ID}:${DATASET}" 2>/dev/null || echo "  (dataset already exists)"
echo "✓ Dataset: ${DATASET}"

# ─── Step 6: Create BigQuery tables ──────────────────────────────────────────
echo "[6/10] Creating BigQuery tables..."
bq mk --table --schema=./bigquery/sensor_readings_schema.json \
  --time_partitioning_type=DAY \
  --time_partitioning_field=timestamp \
  --clustering_fields=unitId \
  "${DATASET}.sensor_readings" 2>/dev/null || echo "  (sensor_readings exists)"

bq mk --table --schema=./bigquery/alerts_schema.json \
  --time_partitioning_type=DAY \
  --time_partitioning_field=timestamp \
  "${DATASET}.alerts_history" 2>/dev/null || echo "  (alerts_history exists)"

bq mk --table --schema=./bigquery/anomaly_scores_schema.json \
  --time_partitioning_type=DAY \
  --time_partitioning_field=evaluatedAt \
  "${DATASET}.anomaly_scores" 2>/dev/null || echo "  (anomaly_scores exists)"

bq mk --table --schema=./bigquery/maintenance_schema.json \
  --time_partitioning_type=DAY \
  --time_partitioning_field=performedAt \
  "${DATASET}.maintenance_events" 2>/dev/null || echo "  (maintenance_events exists)"

bq mk --table --schema=./bigquery/fleet_reports_schema.json \
  "${DATASET}.fleet_reports" 2>/dev/null || echo "  (fleet_reports exists)"
echo "✓ BigQuery tables created"

# ─── Step 7: Create Pub/Sub topics ───────────────────────────────────────────
echo "[7/10] Creating Pub/Sub topics..."
TOPICS=(
  "smart-cooling-sensor-events"
  "smart-cooling-anomaly-alerts"
  "smart-cooling-agent-triggers"
  "smart-cooling-notifications"
  "smart-cooling-maintenance-commands"
)
for TOPIC in "${TOPICS[@]}"; do
  gcloud pubsub topics create "${TOPIC}" --quiet 2>/dev/null || echo "  (${TOPIC} exists)"
done

# Create subscriptions
gcloud pubsub subscriptions create "anomaly-alerts-sub" \
  --topic="smart-cooling-anomaly-alerts" \
  --quiet 2>/dev/null || true

gcloud pubsub subscriptions create "notifications-sub" \
  --topic="smart-cooling-notifications" \
  --quiet 2>/dev/null || true
echo "✓ Pub/Sub topics created"

# ─── Step 8: Create Cloud Storage buckets ────────────────────────────────────
echo "[8/10] Creating Cloud Storage buckets..."
gsutil mb -l "${REGION}" "gs://smart-cooling-reports-${PROJECT_ID}" 2>/dev/null || true
gsutil mb -l "${REGION}" "gs://smart-cooling-artifacts-${PROJECT_ID}" 2>/dev/null || true
echo "✓ Storage buckets created"

# ─── Step 9: Create Cloud Scheduler jobs ─────────────────────────────────────
echo "[9/10] Creating Cloud Scheduler jobs..."

# Hourly anomaly detection trigger
gcloud scheduler jobs create pubsub smart-cooling-hourly-anomaly \
  --location="${REGION}" \
  --schedule="0 * * * *" \
  --topic="smart-cooling-agent-triggers" \
  --message-body='{"trigger":"anomaly_check","scope":"all_units"}' \
  --quiet 2>/dev/null || echo "  (hourly-anomaly job exists)"

# Daily fleet report at 07:00 IST (01:30 UTC)
gcloud scheduler jobs create pubsub smart-cooling-daily-report \
  --location="${REGION}" \
  --schedule="30 1 * * *" \
  --topic="smart-cooling-agent-triggers" \
  --message-body='{"trigger":"fleet_report","scope":"full"}' \
  --quiet 2>/dev/null || echo "  (daily-report job exists)"

# Every 6 hours: BigQuery ML anomaly detection
gcloud scheduler jobs create pubsub smart-cooling-ml-anomaly \
  --location="${REGION}" \
  --schedule="0 */6 * * *" \
  --topic="smart-cooling-agent-triggers" \
  --message-body='{"trigger":"bigquery_ml_anomaly","scope":"all_units"}' \
  --quiet 2>/dev/null || echo "  (ml-anomaly job exists)"

echo "✓ Cloud Scheduler jobs created"

# ─── Step 10: Deploy ioFog Controller VM ─────────────────────────────────────
echo "[10/10] Creating ioFog Controller VM (e2-micro, free tier)..."
gcloud compute instances create "iofog-controller" \
  --machine-type=e2-micro \
  --zone="${REGION}-a" \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=20GB \
  --tags=iofog-controller \
  --metadata=startup-script='#!/bin/bash
    apt-get update -qq
    apt-get install -y -qq docker.io docker-compose curl wget
    systemctl enable docker
    systemctl start docker
    # Install ioFog Controller
    curl -sSf https://packagecloud.io/install/repositories/iofog/iofog-controller/script.deb.sh | bash
    apt-get install -y iofog-controller
    iofog-controller start
    # Install Eclipse Ditto via Docker Compose
    mkdir -p /opt/ditto
    cd /opt/ditto
    # Ditto docker-compose will be uploaded separately
    echo "Startup complete" > /var/log/iofog-setup.log' \
  --quiet 2>/dev/null || echo "  (VM already exists)"

# Open firewall for ioFog Controller ports
gcloud compute firewall-rules create iofog-controller-ports \
  --allow=tcp:51121,tcp:51120,tcp:80,tcp:8080,tcp:443 \
  --target-tags=iofog-controller \
  --description="ioFog Controller ports" \
  --quiet 2>/dev/null || true

# Get VM external IP
CONTROLLER_IP=$(gcloud compute instances describe iofog-controller \
  --zone="${REGION}-a" \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)' 2>/dev/null)
echo "✓ ioFog Controller VM created"
echo "  External IP: ${CONTROLLER_IP}"
echo ""

# ─── Summary ─────────────────────────────────────────────────────────────────
echo "========================================================"
echo "  GCP Setup Complete!"
echo "========================================================"
echo ""
echo "  Next steps:"
echo "  1. Add this to your .env file:"
echo "     IOFOG_CONTROLLER_IP=${CONTROLLER_IP}"
echo ""
echo "  2. Wait ~3 minutes for the VM startup script to finish"
echo "  3. Verify Controller is running:"
echo "     ssh <user>@${CONTROLLER_IP}"
echo "     iofog-controller status"
echo ""
echo "  4. Run: iofogctl configure controlplane --kube-config ./iofog/controlplane.yaml"
echo ""
echo "  IMPORTANT: gcp/service-account.json is your GCP key."
echo "             Never commit it. Never share it."
echo "========================================================"
