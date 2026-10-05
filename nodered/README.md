# Node-RED Flow Configuration

## Overview

Node-RED serves as the central orchestration and processing layer in the Smart Cold Storage Digital Twin system. It receives sensor data from MQTT, validates and processes it, writes to InfluxDB for historical storage, updates Eclipse Ditto digital twins, and performs condition checking for abnormal behavior detection.

## Flow Architecture

```
MQTT Input → Parse/Validate → ┬→ InfluxDB Write
                               ├→ Ditto Update
                               └→ Condition Check → Alert Handler → ┬→ MQTT Alerts
                                                                     └→ InfluxDB Alerts
```

## Main Flow Components

### 1. MQTT Input Node

**Purpose**: Subscribe to all cold storage sensor data

- **Topic**: `coldstorage/+/data`
- **QoS**: 1 (at least once delivery)
- **Data Type**: JSON
- **Broker**: Mosquitto (mosquitto:1883)

**Expected Message Format**:
```json
{
  "unitId": "CS-01",
  "temperature": 4.2,
  "humidity": 67,
  "compressorStatus": "ON",
  "energyConsumption": 2.3,
  "timestamp": "2026-10-05T10:30:00Z"
}
```

### 2. Parse and Validate Node

**Purpose**: Parse incoming JSON and validate required fields

**Validation Checks**:
- `unitId` exists
- `temperature` is defined and numeric
- `humidity` is defined and numeric
- `compressorStatus` exists
- `energyConsumption` is defined and numeric
- `timestamp` exists (or use current time)

**Output**: 
- `msg.sensorData`: Validated sensor data
- `msg.unitId`: Unit identifier for routing
- `msg.topic`: Set to unitId for routing

### 3. InfluxDB Write Path

**Components**:
- **Prepare InfluxDB Write**: Converts to line protocol
- **InfluxDB Out Node**: Writes to InfluxDB

**Line Protocol Format**:
```
sensor_data,unitId=CS-01 temperature=4.2,humidity=67,compressorStatus="ON",energyConsumption=2.3 1696507800000000000
```

**Configuration**:
- Bucket: `cold_storage`
- Organization: `smart_cooling`
- Precision: nanoseconds
- Measurement: `sensor_data`

### 4. Ditto Update Path

**Components**:
- **Prepare Ditto Update**: Creates PATCH payload
- **HTTP Request**: Updates Thing via Ditto API

**Ditto Update Payload**:
```json
{
  "features": {
    "temperature": {
      "properties": {
        "value": 4.2,
        "status": "normal",
        "lastUpdated": "2026-10-05T10:30:00Z"
      }
    },
    "humidity": {
      "properties": {
        "value": 67,
        "status": "normal",
        "lastUpdated": "2026-10-05T10:30:00Z"
      }
    },
    "compressor": {
      "properties": {
        "status": "ON",
        "lastUpdated": "2026-10-05T10:30:00Z"
      }
    },
    "energy": {
      "properties": {
        "consumption": 2.3,
        "efficiency": "normal",
        "lastUpdated": "2026-10-05T10:30:00Z"
      }
    },
    "connectivity": {
      "properties": {
        "connected": true,
        "lastSeen": "2026-10-05T10:30:00Z"
      }
    }
  }
}
```

**API Configuration**:
- Method: PATCH
- URL: `http://ditto-gateway:8080/api/2/things/org.eclipse.ditto:{unitId}`
- Headers: `Content-Type: application/merge-patch+json`

### 5. Condition Detection

**Purpose**: Identify abnormal conditions based on thresholds

**Thresholds**:

| Parameter | Critical High | Warning High | Normal High | Normal Low | Warning Low | Critical Low |
|-----------|--------------|--------------|-------------|------------|-------------|--------------|
| Temperature | 10.0°C | 8.0°C | 6.0°C | 2.0°C | 0.0°C | -2.0°C |
| Humidity | - | 80% | - | 50% | - | - |
| Energy | 4.0 kW | 3.0 kW | - | - | - | - |

**Alert Types**:
- `temperature_critical_high`
- `temperature_warning_high`
- `temperature_warning_low`
- `temperature_critical_low`
- `humidity_out_of_range`
- `energy_warning`
- `energy_critical`

**Alert Structure**:
```json
{
  "unitId": "CS-01",
  "alertType": "temperature_warning_high",
  "severity": "warning",
  "message": "Temperature above normal: 8.5°C",
  "value": 8.5,
  "threshold": 8.0,
  "timestamp": "2026-10-05T10:30:00Z"
}
```

### 6. Alert Handler

**Purpose**: Process and distribute alerts

**Actions**:
1. Publish alert to MQTT topic `coldstorage/{unitId}/alerts`
2. Write alert to InfluxDB `alerts` bucket
3. Log to debug console

**MQTT Alert Configuration**:
- QoS: 2 (exactly once delivery)
- Retain: false
- Topic: `coldstorage/{unitId}/alerts`

**InfluxDB Alert Storage**:
```
alerts,unitId=CS-01,alertType=temperature_warning_high,severity=warning message="Temperature above normal",value=8.5,threshold=8.0,resolved=false
```

## Configuration

### MQTT Broker Configuration

```javascript
{
  "name": "Mosquitto",
  "broker": "mosquitto",
  "port": "1883",
  "clientid": "nodered",
  "keepalive": "60",
  "cleansession": true
}
```

### InfluxDB Configuration

```javascript
{
  "hostname": "influxdb",
  "port": "8086",
  "protocol": "http",
  "influxdbVersion": "2.0",
  "url": "http://influxdb:8086",
  "org": "smart_cooling",
  "token": "smart-cooling-super-secret-token"
}
```

## Global Context Variables

Accessible via `context.global` in function nodes:

```javascript
{
  systemName: 'Smart Cold Storage Digital Twin',
  thresholds: {
    temperature: {
      critical_high: 10.0,
      warning_high: 8.0,
      normal_high: 6.0,
      normal_low: 2.0,
      warning_low: 0.0,
      critical_low: -2.0
    },
    humidity: {
      high: 80,
      low: 50
    },
    energy: {
      warning: 3.0,
      critical: 4.0
    },
    compressor: {
      max_runtime_seconds: 3600,
      max_cycles_per_hour: 10
    }
  },
  services: {
    influxdb: 'http://influxdb:8086',
    ditto: 'http://ditto-gateway:8080',
    mqtt: 'mqtt://mosquitto:1883'
  }
}
```

## Installing Additional Nodes

Node-RED needs these additional nodes:

```bash
# In Node-RED container
npm install node-red-contrib-influxdb
npm install node-red-dashboard
npm install @influxdata/influxdb-client
```

Or install via the Node-RED palette manager:
1. Open Node-RED UI: http://localhost:1880
2. Menu → Manage palette
3. Install tab
4. Search and install:
   - node-red-contrib-influxdb
   - node-red-dashboard

## Flow Import

To import the flows into Node-RED:

1. Open Node-RED UI: http://localhost:1880
2. Menu → Import
3. Select a file to import
4. Choose `flows.json`
5. Click Import

Or copy the contents of `flows.json` and paste into the import dialog.

## Testing the Flow

### 1. Test with MQTT

Publish a test message:

```bash
docker exec -it smart_cooling_mosquitto mosquitto_pub \
  -t "coldstorage/CS-01/data" \
  -m '{"unitId":"CS-01","temperature":4.2,"humidity":67,"compressorStatus":"ON","energyConsumption":2.3,"timestamp":"2026-10-05T10:30:00Z"}'
```

### 2. Verify InfluxDB Write

Query InfluxDB to verify data was written:

```bash
curl -XPOST 'http://localhost:8086/api/v2/query?org=smart_cooling' \
  --header 'Authorization: Token smart-cooling-super-secret-token' \
  --header 'Content-Type: application/vnd.flux' \
  --data 'from(bucket:"cold_storage") |> range(start: -1h) |> filter(fn: (r) => r["unitId"] == "CS-01")'
```

### 3. Verify Ditto Update

Check the digital twin was updated:

```bash
curl http://localhost:8080/api/2/things/org.eclipse.ditto:CS-01
```

### 4. Test Alert Generation

Publish a message with high temperature:

```bash
docker exec -it smart_cooling_mosquitto mosquitto_pub \
  -t "coldstorage/CS-01/data" \
  -m '{"unitId":"CS-01","temperature":9.5,"humidity":67,"compressorStatus":"ON","energyConsumption":2.3,"timestamp":"2026-10-05T10:35:00Z"}'
```

Subscribe to alerts:

```bash
docker exec -it smart_cooling_mosquitto mosquitto_sub -t "coldstorage/+/alerts" -v
```

## Debugging

### Enable Debug Nodes

1. Open Node-RED UI
2. Deploy the flow
3. Open Debug sidebar (right panel)
4. Enable debug nodes:
   - Debug Raw MQTT (currently disabled)
   - Debug Alerts (currently enabled)

### View Function Node Errors

Function nodes log errors to the debug sidebar. Check for:
- Parse errors
- Validation failures
- HTTP request failures
- InfluxDB write errors

### Check Node Status

Nodes show status indicators:
- **Green dot**: Successfully processed
- **Red ring**: Error occurred
- **Blue dot**: Message received
- **Yellow ring**: Warning

### View Logs

```bash
# Node-RED logs
docker-compose logs nodered

# All services
docker-compose logs -f
```

## Performance Considerations

### Message Rate

The flow is designed to handle:
- **Normal rate**: 1 message/second per unit (3/second total for 3 units)
- **Burst rate**: Up to 10 messages/second per unit
- **Max throughput**: ~100 messages/second total

### Optimization Tips

1. **Disable unnecessary debug nodes** in production
2. **Use batch writes** for InfluxDB if high frequency
3. **Implement message queuing** for MQTT reliability
4. **Monitor Node-RED memory usage**
5. **Use persistent context** for stateful operations

### Monitoring

Monitor Node-RED performance:

```bash
# Check memory usage
docker stats smart_cooling_nodered

# Check CPU usage
docker exec smart_cooling_nodered top -bn1
```

## Advanced Flows

### Trend Analysis Flow

Add nodes to calculate:
- Moving averages
- Rate of change
- Statistical anomalies

### Predictive Maintenance Flow

Implement multi-signal analysis:
- Query recent historical data from InfluxDB
- Calculate maintenance score
- Update Ditto maintenance feature
- Generate predictive alerts

### Data Quality Flow

Monitor data quality:
- Check for missing messages
- Detect sensor failures
- Validate data ranges
- Alert on communication issues

## Troubleshooting

### MQTT Connection Issues

```javascript
// Check MQTT broker status
// In Node-RED function node:
const mqtt = global.get('mqtt_client');
if (mqtt && mqtt.connected) {
    node.status({fill:"green",shape:"dot",text:"connected"});
} else {
    node.status({fill:"red",shape:"ring",text:"disconnected"});
}
```

### InfluxDB Write Failures

Check:
1. InfluxDB container is running
2. Token is correct
3. Bucket exists
4. Line protocol is valid
5. Network connectivity

### Ditto Update Failures

Check:
1. Ditto gateway is accessible
2. Thing exists in Ditto
3. Payload format is correct
4. HTTP timeout settings
5. Network connectivity

## Best Practices

1. **Error Handling**: Always handle errors in function nodes
2. **Validation**: Validate all incoming data
3. **Logging**: Use appropriate log levels
4. **Status Indicators**: Update node status for visibility
5. **Documentation**: Comment complex function nodes
6. **Testing**: Test with various input scenarios
7. **Monitoring**: Monitor flow performance
8. **Version Control**: Export and version flows regularly

## Security

### Production Configuration

For production deployment:

1. **Enable authentication**:
```javascript
adminAuth: {
    type: "credentials",
    users: [{
        username: "admin",
        password: "$2a$08$...", // bcrypt hash
        permissions: "*"
    }]
}
```

2. **Use HTTPS**: Configure TLS for Node-RED UI

3. **Secure MQTT**: Use authentication and TLS

4. **Environment Variables**: Store sensitive data in environment variables

5. **Network Isolation**: Use Docker networks appropriately

## References

- [Node-RED Documentation](https://nodered.org/docs/)
- [Node-RED Cookbook](https://cookbook.nodered.org/)
- [Function Node API](https://nodered.org/docs/user-guide/writing-functions)
- [MQTT Node](https://flows.nodered.org/node/node-red-contrib-mqtt-broker)
- [InfluxDB Node](https://flows.nodered.org/node/node-red-contrib-influxdb)
