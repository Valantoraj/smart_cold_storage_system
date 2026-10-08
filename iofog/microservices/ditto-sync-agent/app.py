#!/usr/bin/env python3
"""
Ditto Sync Agent — Placeholder
Full implementation in Phase 2.
"""
import os, time, logging

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("ditto-sync")

UNIT_IDS = os.environ.get("UNIT_IDS", "CS-01,CS-02").split(",")
DITTO_URL = os.environ.get("DITTO_URL", "http://ditto-gateway:8080")

log.info(f"Ditto Sync Agent — Phase 2 placeholder")
log.info(f"Units: {UNIT_IDS}, Ditto: {DITTO_URL}")
log.info(f"Full implementation coming in Phase 2.")

while True:
    time.sleep(60)
