#!/usr/bin/env python3
"""
Edge Anomaly Detector — Placeholder
Full implementation in Phase 2.
"""
import os, time, logging

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("edge-anomaly")

UNIT_IDS = os.environ.get("UNIT_IDS", "CS-01,CS-02").split(",")
WAREHOUSE_ID = os.environ.get("WAREHOUSE_ID", "alpha")
INTERVAL = int(os.environ.get("SCAN_INTERVAL_SECONDS", "30"))

log.info(f"Edge Anomaly Detector — Phase 2 placeholder")
log.info(f"Units: {UNIT_IDS}, Warehouse: {WAREHOUSE_ID}")
log.info(f"Full implementation coming in Phase 2.")

while True:
    log.info(f"[placeholder] Scan interval {INTERVAL}s — awaiting Phase 2 implementation")
    time.sleep(INTERVAL)
