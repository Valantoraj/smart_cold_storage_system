#!/usr/bin/env bash
# build-push-images.sh — Build and push all cold-twin container images
# Usage: ./scripts/build-push-images.sh [component]
# component: all | sensor-simulator | mosquitto-edge | nodered-edge |
#            mosquitto-fog | nodered-fog | cloud-bridge
# Reads IMAGE_PREFIX and IMAGE_TAG from config/topology.env if present.

set -euo pipefail
cd "$(dirname "$0")/.."

# Load topology.env if present
if [ -f config/topology.env ]; then
    set -a; source config/topology.env; set +a
fi

IMAGE_PREFIX="${IMAGE_PREFIX:-us-central1-docker.pkg.dev/project-f47e3be0-07f0-4225-b8e/coldtwin}"
IMAGE_TAG="${IMAGE_TAG:-1.0.0}"
COMPONENT="${1:-all}"
PLATFORM="linux/amd64"

_build_push() {
    local name="$1"
    local context="$2"
    local image="${IMAGE_PREFIX}/${name}:${IMAGE_TAG}"
    echo ""
    echo "=== Building ${image} ==="
    # Copy shared config into build context
    mkdir -p "${context}/config"
    cp config/units.json "${context}/config/" 2>/dev/null || true
    cp config/rules.json "${context}/config/" 2>/dev/null || true

    docker build --platform="${PLATFORM}" -t "${image}" "${context}"
    echo "=== Pushing ${image} ==="
    docker push "${image}"
    echo "  + ${name} done"
}

gcloud auth configure-docker us-central1-docker.pkg.dev --quiet 2>/dev/null || true

case "$COMPONENT" in
    sensor-simulator)
        _build_push sensor-simulator edge/simulator ;;
    mosquitto-edge)
        _build_push mosquitto-edge edge/mosquitto-edge ;;
    nodered-edge)
        _build_push nodered-edge edge/nodered-edge ;;
    mosquitto-fog)
        _build_push mosquitto-fog fog/mosquitto-fog ;;
    nodered-fog)
        _build_push nodered-fog fog/nodered-fog ;;
    cloud-bridge)
        _build_push cloud-bridge fog/cloud-bridge ;;
    all)
        _build_push sensor-simulator  edge/simulator
        _build_push mosquitto-edge    edge/mosquitto-edge
        _build_push nodered-edge      edge/nodered-edge
        _build_push mosquitto-fog     fog/mosquitto-fog
        _build_push nodered-fog       fog/nodered-fog
        _build_push cloud-bridge      fog/cloud-bridge
        echo ""
        echo "=== All images built and pushed ==="
        ;;
    *)
        echo "Unknown component: $COMPONENT"
        echo "Usage: $0 [all|sensor-simulator|mosquitto-edge|nodered-edge|mosquitto-fog|nodered-fog|cloud-bridge]"
        exit 1 ;;
esac
