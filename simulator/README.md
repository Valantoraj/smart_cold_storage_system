# Smart Cold Storage Sensor Simulator

## Overview

The sensor simulator generates realistic sensor data for cold storage units, including both normal operation and various abnormal scenarios. This is essential for testing the digital twin system's monitoring, alerting, and predictive maintenance capabilities without physical hardware.

## Features

- **Multiple Units**: Simulate multiple cold storage units simultaneously
- **Realistic Behavior**: Temperature, humidity, compressor cycles, and energy consumption
- **Scenario-Based**: Eight different scenarios including normal and abnormal conditions
- **MQTT Integration**: Publishes data directly to the MQTT broker
- **Configurable**: Adjustable intervals, duration, and unit configurations

## Installation

### Prerequisites

- Python 3.8 or higher
- pip (Python package installer)

### Install Dependencies

```bash
cd simulator
pip install -r requirements.txt
```

Or install manually:

```bash
pip install paho-mqtt
```

## Usage

### Basic Usage

Run with default settings (3 units in normal operation):

```bash
python sensor_simulator.py
```

This will simulate:
- CS-01 with normal operation
- CS-02 with normal operation
- CS-03 with normal operation

### Custom Units and Scenarios

Specify units and their scenarios:

```bash
python sensor_simulator.py --units CS-01:normal CS-02:temp_rising CS-03:high_energy
```

### Adjust Update Interval

Change how frequently data is published (in seconds):

```bash
# Update every 10 seconds (for faster testing)
python sensor_simulator.py --interval 10

# Update every 5 minutes
python sensor_simulator.py --interval 300
```

### Run for Specific Duration

Limit the simulation duration:

```bash
# Run for 10 minutes (600 seconds)
python sensor_simulator.py --duration 600

# Run for 1 hour
python sensor_simulator.py --duration 3600
```

### Connect to Remote MQTT Broker

```bash
python sensor_simulator.py --mqtt-host 192.168.1.100 --mqtt-port 1883
```

### Docker Environment

When running with Docker Compose:

```bash
# From the host machine
python sensor_simulator.py --mqtt-host localhost --mqtt-port 1883

# Or from inside the Docker network (if simulator is containerized)
python sensor_simulator.py --mqtt-host mosquitto --mqtt-port 1883
```

## Available Scenarios

### 1. Normal Operation (`normal`)

**Behavior**:
- Temperature: 2-6°C with small fluctuations
- Humidity: 60-70% stable
- Compressor: Regular cycles (ON/OFF)
- Energy: 2-3 kW normal consumption

**Use Case**: Baseline testing, normal dashboard display

**Example**:
```bash
python sensor_simulator.py --units CS-01:normal
```

### 2. Temperature Rising (`temp_rising`)

**Behavior**:
- Temperature: Gradually increasing from 4°C upward
- Compressor: Running more frequently but less effective
- Energy: Gradually increasing
- Humidity: Slightly rising

**Use Case**: Test cooling system degradation detection

**Indicators of Problem**:
- Temperature exceeds 6°C (warning) then 8°C (critical)
- Compressor runtime increasing
- Energy consumption trending up
- Should trigger predictive maintenance alert

**Example**:
```bash
python sensor_simulator.py --units CS-01:temp_rising --interval 30 --duration 1800
```

### 3. Temperature Fluctuating (`temp_fluctuating`)

**Behavior**:
- Temperature: Large swings (2-8°C)
- Compressor: Very frequent cycling
- Energy: Variable
- Humidity: Unstable

**Use Case**: Test thermostat or control system malfunction detection

**Indicators of Problem**:
- Excessive compressor cycles
- Temperature instability
- Should alert on control system issue

**Example**:
```bash
python sensor_simulator.py --units CS-02:temp_fluctuating
```

### 4. High Energy Consumption (`high_energy`)

**Behavior**:
- Temperature: Normal range (2-6°C)
- Compressor: Normal operation
- Energy: 1.5x normal (3-4.5 kW)
- Humidity: Normal

**Use Case**: Test energy efficiency monitoring

**Indicators of Problem**:
- Energy consumption above 3kW warning threshold
- Temperature maintained but at higher cost
- Should suggest maintenance or inspection

**Example**:
```bash
python sensor_simulator.py --units CS-03:high_energy
```

### 5. Humidity Issue (`humidity_issue`)

**Behavior**:
- Temperature: Mostly normal
- Humidity: Drifting upward toward 80-85%
- Compressor: Normal operation
- Energy: Normal

**Use Case**: Test humidity monitoring and door seal issues

**Indicators of Problem**:
- Humidity exceeds 80% threshold
- Suggests door seal problem or dehumidification issue

**Example**:
```bash
python sensor_simulator.py --units CS-01:humidity_issue
```

### 6. Equipment Degradation (`equipment_degradation`)

**Behavior**:
- Temperature: Slowly rising
- Compressor: Running longer with less effectiveness
- Energy: Gradually increasing
- Humidity: Less stable

**Use Case**: Test predictive maintenance multi-signal detection

**Indicators of Problem**:
- Temperature trend + energy trend + compressor runtime all increasing
- Perfect for testing predictive maintenance logic
- Should generate predictive maintenance alert

**Example**:
```bash
python sensor_simulator.py --units CS-02:equipment_degradation --interval 20
```

### 7. Door Open (`door_open`)

**Behavior**:
- Temperature: Rapidly increasing (up to 15°C)
- Humidity: Rapidly increasing (up to 90%)
- Compressor: Running continuously
- Energy: High consumption

**Use Case**: Test rapid condition change detection

**Indicators of Problem**:
- Quick temperature spike
- Humidity spike
- Immediate critical alerts
- Suggests door left open

**Example**:
```bash
python sensor_simulator.py --units CS-03:door_open --interval 10 --duration 300
```

### 8. Compressor Failure (`compressor_failure`)

**Behavior**:
- Temperature: Steadily rising
- Compressor: Stuck OFF (not running)
- Energy: Near zero (0.1-0.3 kW standby only)
- Humidity: Rising

**Use Case**: Test complete equipment failure detection

**Indicators of Problem**:
- Temperature rising
- Compressor always OFF
- Energy consumption near zero
- Critical failure alert

**Example**:
```bash
python sensor_simulator.py --units CS-01:compressor_failure --interval 30
```

## Complete Testing Examples

### Scenario 1: Normal Operations Monitoring

Test basic monitoring with all units operating normally:

```bash
python sensor_simulator.py \
  --units CS-01:normal CS-02:normal CS-03:normal \
  --interval 60 \
  --duration 3600
```

**Expected Results**:
- All units show green/healthy status in dashboard
- Temperature stays in 2-6°C range
- No alerts generated
- Compressor cycles normally

### Scenario 2: Predictive Maintenance Detection

Test multi-signal predictive maintenance:

```bash
python sensor_simulator.py \
  --units CS-01:normal CS-02:equipment_degradation CS-03:normal \
  --interval 30 \
  --duration 1800
```

**Expected Results**:
- CS-02 generates predictive maintenance alert after ~10-15 minutes
- Temperature, energy, and compressor trends all show degradation
- Maintenance score increases
- Warning alerts before critical threshold

### Scenario 3: Multiple Concurrent Issues

Test system with multiple problems:

```bash
python sensor_simulator.py \
  --units CS-01:temp_rising CS-02:high_energy CS-03:humidity_issue \
  --interval 45 \
  --duration 2400
```

**Expected Results**:
- Different alert types for each unit
- Dashboard shows multiple units with issues
- Alert dashboard populated with various severities

### Scenario 4: Critical Failure

Test immediate critical response:

```bash
python sensor_simulator.py \
  --units CS-01:door_open CS-02:compressor_failure CS-03:normal \
  --interval 20 \
  --duration 600
```

**Expected Results**:
- Immediate critical alerts
- Rapid dashboard status changes
- MQTT alert messages published
- Alert history in InfluxDB

### Scenario 5: Rapid Testing

Quick iteration for development:

```bash
python sensor_simulator.py \
  --units CS-01:temp_rising \
  --interval 5 \
  --duration 120
```

**Expected Results**:
- Fast data generation for quick testing
- Trends visible in short time
- Good for UI development

## Output Format

The simulator publishes JSON messages to MQTT topics:

**Topic**: `coldstorage/{unitId}/data`

**Payload**:
```json
{
  "unitId": "CS-01",
  "temperature": 4.2,
  "humidity": 67.0,
  "compressorStatus": "ON",
  "energyConsumption": 2.35,
  "timestamp": "2026-10-05T10:30:00.000000+00:00"
}
```

## Console Output

The simulator prints readings to console:

```
Added unit CS-01 with scenario 'normal'
Added unit CS-02 with scenario 'temp_rising'
Connected to MQTT broker at localhost:1883

================================================================================
Starting simulation with 2 units
Publishing interval: 60 seconds
================================================================================

--- Iteration 1 ---
[2026-10-05T10:30:00+00:00] CS-01: Temp=4.15°C, Humidity=65.2%, Compressor=OFF, Energy=0.18kW
[2026-10-05T10:30:00+00:00] CS-02: Temp=4.35°C, Humidity=66.1%, Compressor=ON, Energy=2.67kW

--- Iteration 2 ---
[2026-10-05T10:31:00+00:00] CS-01: Temp=4.28°C, Humidity=64.8%, Compressor=OFF, Energy=0.22kW
[2026-10-05T10:31:00+00:00] CS-02: Temp=4.42°C, Humidity=66.5%, Compressor=ON, Energy=2.75kW
```

## Monitoring the Simulation

### Subscribe to MQTT Topics

```bash
# All data
docker exec -it smart_cooling_mosquitto mosquitto_sub -t "coldstorage/+/data" -v

# Specific unit
docker exec -it smart_cooling_mosquitto mosquitto_sub -t "coldstorage/CS-01/data" -v

# All alerts
docker exec -it smart_cooling_mosquitto mosquitto_sub -t "coldstorage/+/alerts" -v
```

### Check Data in InfluxDB

```bash
# Using InfluxDB CLI
docker exec -it smart_cooling_influxdb \
  influx query 'from(bucket:"cold_storage") |> range(start: -1h) |> filter(fn: (r) => r["unitId"] == "CS-01")' \
  --org smart_cooling --token smart-cooling-super-secret-token
```

### View in Grafana

1. Open Grafana: http://localhost:3000
2. Navigate to Cold Storage Dashboard
3. See real-time updates from simulator

### Check Digital Twins

```bash
# Get current state
curl http://localhost:8080/api/2/things/org.eclipse.ditto:CS-01

# Get temperature feature
curl http://localhost:8080/api/2/things/org.eclipse.ditto:CS-01/features/temperature
```

## Stopping the Simulator

Press `Ctrl+C` to stop the simulator gracefully:

```
^C
Simulation stopped by user

Simulator stopped
```

## Troubleshooting

### Cannot Connect to MQTT Broker

**Error**: `Failed to connect to MQTT broker`

**Solutions**:
1. Check if Mosquitto is running: `docker ps | grep mosquitto`
2. Verify port is accessible: `telnet localhost 1883`
3. Check firewall settings
4. Try with `--mqtt-host localhost` explicitly

### No Data Appearing in System

**Checks**:
1. Verify MQTT connection succeeded (check console output)
2. Check Node-RED is receiving messages (Node-RED debug panel)
3. Verify InfluxDB is writing data
4. Check Ditto is being updated

### Simulator Runs Too Fast/Slow

Adjust the interval:
```bash
# Faster
python sensor_simulator.py --interval 10

# Slower
python sensor_simulator.py --interval 120
```

## Advanced Usage

### Creating Custom Scenarios

Edit `sensor_simulator.py` and add to `scenarios` dict in `_init_scenario()`:

```python
"custom_scenario": {
    "temp_variance": 0.5,
    "humidity_variance": 3.0,
    "energy_variance": 0.2,
    "compressor_cycle_time": 500
}
```

Then implement the behavior in a new method like `_simulate_custom_scenario()`.

### Running as Background Process

```bash
# Linux/Mac
nohup python sensor_simulator.py > simulator.log 2>&1 &

# Windows PowerShell
Start-Process python -ArgumentList "sensor_simulator.py" -NoNewWindow -RedirectStandardOutput simulator.log
```

### Integration Testing

Create a test script:

```bash
#!/bin/bash
# test_scenarios.sh

echo "Test 1: Normal operation"
python sensor_simulator.py --units CS-01:normal --interval 5 --duration 60

echo "Test 2: Temperature rising"
python sensor_simulator.py --units CS-01:temp_rising --interval 5 --duration 120

echo "Test 3: Multiple issues"
python sensor_simulator.py --units CS-01:temp_rising CS-02:high_energy --interval 5 --duration 180
```

## Tips

1. **Start with fast intervals** (`--interval 5`) for initial testing
2. **Use duration limits** to avoid filling up storage during development
3. **Test one scenario at a time** initially to understand behavior
4. **Monitor logs** in Node-RED and other services while simulator runs
5. **Reset data** between tests for clean comparisons
6. **Save configurations** for reproducible test scenarios

## References

- [Paho MQTT Python](https://www.eclipse.org/paho/index.php?page=clients/python/index.php)
- [MQTT Protocol](https://mqtt.org/)
- Python `argparse` for command-line arguments
- Python `dataclasses` for data structures
