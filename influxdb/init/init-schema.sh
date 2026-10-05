#!/bin/bash
# InfluxDB Initialization Script
# This script runs automatically when InfluxDB container starts for the first time

echo "Starting InfluxDB initialization..."

# Wait for InfluxDB to be ready
until influx ping &> /dev/null; do
  echo "Waiting for InfluxDB to be ready..."
  sleep 2
done

echo "InfluxDB is ready. Configuring schema..."

# Environment variables are set in docker-compose.yml
# DOCKER_INFLUXDB_INIT_MODE=setup
# DOCKER_INFLUXDB_INIT_USERNAME=admin
# DOCKER_INFLUXDB_INIT_PASSWORD=adminpass123
# DOCKER_INFLUXDB_INIT_ORG=smart_cooling
# DOCKER_INFLUXDB_INIT_BUCKET=cold_storage
# DOCKER_INFLUXDB_INIT_ADMIN_TOKEN=smart-cooling-super-secret-token

# The bucket is already created by the init setup
# Additional buckets can be created here if needed

echo "Creating additional buckets..."

# Create alerts bucket for storing alert history
influx bucket create \
  --name alerts \
  --org smart_cooling \
  --retention 365d \
  --token smart-cooling-super-secret-token \
  2>/dev/null || echo "Alerts bucket already exists"

# Create analytics bucket for aggregated data
influx bucket create \
  --name analytics \
  --org smart_cooling \
  --retention 730d \
  --token smart-cooling-super-secret-token \
  2>/dev/null || echo "Analytics bucket already exists"

# Create downsampled bucket for long-term storage
influx bucket create \
  --name cold_storage_downsampled \
  --org smart_cooling \
  --retention 1825d \
  --token smart-cooling-super-secret-token \
  2>/dev/null || echo "Downsampled bucket already exists"

echo "InfluxDB initialization completed!"
