# Refrigeration System Runbook
## Cold Storage Unit Maintenance Guide

### Fault Classifications

#### compressor_degradation
**Symptoms:** Temperature rising slowly, compressor duty increasing beyond 65%, on-power increasing beyond baseline × 1.1, all three signals rising together over 10+ minutes.
**Root causes:** Refrigerant leak, compressor wear, condenser coil fouling.
**Action:** Schedule compressor inspection within 48 hours. Check refrigerant charge. Clean condenser coils.
**Urgency:** high

#### door_open
**Symptoms:** Temperature and humidity spike simultaneously within 2-3 minutes. Temperature rise > 0.5°C/min. Humidity rise > 5%/min.
**Root causes:** Door left open, door seal failure.
**Action:** Check door immediately. Inspect door seal. Not an equipment fault — do NOT recommend compressor service.
**Urgency:** medium

#### sensor_spike
**Symptoms:** Single reading far outside normal range (e.g. 25°C in a 4°C unit). Immediately returns to normal.
**Root causes:** EMI interference, loose sensor connection, sensor glitch.
**Action:** Flag reading as suspect. Monitor for recurrence. If repeated, replace sensor.
**Urgency:** low — do NOT generate PM_WARNING for single spike.

#### humidity_drift
**Symptoms:** Humidity gradually climbing over 30+ minutes. Temperature normal.
**Root causes:** Drain blockage, dehumidifier fault, door seal degradation.
**Action:** Check drain line. Inspect door seals. Service dehumidifier.
**Urgency:** medium

#### sensor_dropout
**Symptoms:** No readings for 60-90 seconds from one unit. Other units normal.
**Root causes:** Network/MQTT issue, sensor power loss, edge node fault.
**Action:** Check edge node connectivity. Verify sensor power. Check MQTT broker.
**Urgency:** medium (data loss concern)

### Health State Machine
- OK → WARNING: PM_WARNING fires (3 consecutive evaluations with slope ≥ 0.03°C/min AND duty ≥ 1.3× AND on-power ≥ 1.1×)
- WARNING → CRITICAL: Temperature above hard limit (8.0°C) for ≥ 2 minutes
- CRITICAL/WARNING → OK: 5 consecutive clean evaluations

### Thresholds
- Hard limit: 8.0°C (all units)
- Setpoint CS-01/CS-02: 4.0°C
- Setpoint CS-03: 5.0°C
- Normal compressor duty: 35-45%
- Normal on-power: ~2.0 kW
