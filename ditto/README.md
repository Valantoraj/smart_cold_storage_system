# Eclipse Ditto Digital Twin Configuration

## Overview

Eclipse Ditto provides the digital twin layer for the Smart Cold Storage system. Each physical cold storage unit (CS-01, CS-02, CS-03, etc.) has a corresponding digital twin representation that maintains the current state of the physical asset.

## Architecture

```
Physical Asset (CS-01) ←→ Digital Twin (org.eclipse.ditto:CS-01)
     ↓                              ↓
  Sensor Data                  Thing Features
     ↓                              ↓
  MQTT → Node-RED → Ditto Gateway
```

## Thing Model Structure

### Thing ID Format

```
org.eclipse.ditto:<UnitID>
```

Examples:
- `org.eclipse.ditto:CS-01`
- `org.eclipse.ditto:CS-02`
- `org.eclipse.ditto:CS-03`

### Thing Components

1. **Thing ID**: Unique identifier for the digital twin
2. **Policy ID**: Reference to access control policy
3. **Definition**: Semantic model definition
4. **Attributes**: Static metadata about the physical asset
5. **Features**: Dynamic state and capabilities

## Attributes

Static information about the cold storage unit:

| Attribute | Type | Description | Example |
|-----------|------|-------------|---------|
| manufacturer | string | Equipment manufacturer | "ColdTech Industries" |
| model | string | Model number | "CT-5000" |
| serialNumber | string | Unique serial number | "CS01-2025-001" |
| location | string | Physical location | "Warehouse A - Section 1" |
| building | string | Building identifier | "Main Facility" |
| capacity | string | Storage capacity | "1000 cubic meters" |
| installDate | string | Installation date | "2025-01-15" |
| warrantyExpiration | string | Warranty end date | "2028-01-15" |
| lastMaintenanceDate | string | Last maintenance | "2026-08-15" |
| maintenanceSchedule | string | Maintenance frequency | "quarterly" |
| description | string | Unit description | "Primary cold storage unit" |

## Features

Dynamic state representing current conditions:

### 1. Temperature Feature

Monitors refrigeration temperature.

```json
{
  "temperature": {
    "properties": {
      "value": 4.2,
      "unit": "celsius",
      "status": "normal",
      "target": 4.0,
      "min": 2.0,
      "max": 6.0,
      "lastUpdated": "2026-10-05T10:30:00Z"
    }
  }
}
```

**Status values**: `normal`, `warning`, `critical`

### 2. Humidity Feature

Monitors moisture levels.

```json
{
  "humidity": {
    "properties": {
      "value": 67.0,
      "unit": "percent",
      "status": "normal",
      "target": 65.0,
      "min": 50.0,
      "max": 80.0,
      "lastUpdated": "2026-10-05T10:30:00Z"
    }
  }
}
```

### 3. Compressor Feature

Tracks refrigeration compressor state.

```json
{
  "compressor": {
    "properties": {
      "status": "ON",
      "runtime": 3600,
      "cycles": 24,
      "lastStartTime": "2026-10-05T09:30:00Z",
      "lastStopTime": "2026-10-05T08:45:00Z",
      "totalRuntime": 145800,
      "health": "healthy",
      "lastUpdated": "2026-10-05T10:30:00Z"
    }
  }
}
```

**Status values**: `ON`, `OFF`
**Health values**: `healthy`, `degraded`, `faulty`

### 4. Energy Feature

Monitors power consumption.

```json
{
  "energy": {
    "properties": {
      "consumption": 2.3,
      "unit": "kW",
      "efficiency": "normal",
      "totalConsumption": 5467.8,
      "peakConsumption": 3.2,
      "averageConsumption": 2.1,
      "lastUpdated": "2026-10-05T10:30:00Z"
    }
  }
}
```

**Efficiency values**: `normal`, `inefficient`, `critical`

### 5. Status Feature

Overall system health and operational state.

```json
{
  "status": {
    "properties": {
      "operational": true,
      "health": "healthy",
      "healthScore": 95,
      "lastMaintenance": "2026-08-15",
      "nextMaintenance": "2026-11-15",
      "alerts": [
        {
          "type": "temperature_high",
          "severity": "warning",
          "timestamp": "2026-10-05T10:15:00Z",
          "message": "Temperature slightly elevated"
        }
      ],
      "activeAlertCount": 1,
      "lastUpdated": "2026-10-05T10:30:00Z"
    }
  }
}
```

**Health values**: `healthy`, `attention`, `critical`, `offline`

### 6. Connectivity Feature

Network and communication status.

```json
{
  "connectivity": {
    "properties": {
      "connected": true,
      "signalStrength": 95,
      "lastSeen": "2026-10-05T10:30:00Z",
      "uptime": 864000,
      "dataRate": 1.0,
      "errors": 0
    }
  }
}
```

### 7. Maintenance Feature

Predictive maintenance information.

```json
{
  "maintenance": {
    "properties": {
      "score": 23,
      "temperatureStability": 92.0,
      "energyEfficiency": 88.0,
      "compressorHealth": 95.0,
      "recommendation": "Monitor energy consumption trend",
      "priority": "medium",
      "lastCalculated": "2026-10-05T10:30:00Z"
    }
  }
}
```

**Priority values**: `low`, `medium`, `high`, `critical`

## Policy Configuration

The cold storage policy (`cold-storage-policy.json`) defines access control:

### Policy Entries

1. **owner**: Full read/write access
2. **monitoring**: Read-only access for monitoring services
3. **nodered**: Read/write access for data processing
4. **anonymous**: Limited read access for dashboards

### Subjects

- `nginx:ditto`: Owner with full access
- `nginx:monitoring`: Monitoring services
- `nginx:nodered`: Node-RED processing
- `nginx:anonymous`: Public read access

## API Operations

### Base URL

```
http://localhost:8080/api/2
```

### Authentication

Ditto is configured with `ENABLE_PRE_AUTHENTICATION=true` in development mode.

For production, add authentication header:
```
Authorization: Basic <base64(username:password)>
```

### Create Policy

```bash
curl -X PUT http://localhost:8080/api/2/policies/org.eclipse.ditto:cold-storage-policy \
  -H "Content-Type: application/json" \
  -d @ditto/policies/cold-storage-policy.json
```

### Create Thing

```bash
curl -X PUT http://localhost:8080/api/2/things/org.eclipse.ditto:CS-01 \
  -H "Content-Type: application/json" \
  -d @ditto/things/CS-01.json
```

### Get Thing

```bash
curl http://localhost:8080/api/2/things/org.eclipse.ditto:CS-01
```

### Get Specific Feature

```bash
curl http://localhost:8080/api/2/things/org.eclipse.ditto:CS-01/features/temperature
```

### Update Feature Property

```bash
curl -X PUT http://localhost:8080/api/2/things/org.eclipse.ditto:CS-01/features/temperature/properties/value \
  -H "Content-Type: application/json" \
  -d '4.5'
```

### Update Multiple Properties (PATCH)

```bash
curl -X PATCH http://localhost:8080/api/2/things/org.eclipse.ditto:CS-01 \
  -H "Content-Type: application/merge-patch+json" \
  -d '{
    "features": {
      "temperature": {
        "properties": {
          "value": 4.5,
          "status": "warning",
          "lastUpdated": "2026-10-05T10:35:00Z"
        }
      },
      "compressor": {
        "properties": {
          "status": "ON",
          "runtime": 3700
        }
      }
    }
  }'
```

### Search Things

```bash
# Find all things
curl http://localhost:8080/api/2/search/things

# Find things with specific criteria
curl -X POST http://localhost:8080/api/2/search/things \
  -H "Content-Type: application/json" \
  -d '{
    "filter": "eq(attributes/location,\"Warehouse A - Section 1\")"
  }'

# Find things with temperature > 6
curl -X POST http://localhost:8080/api/2/search/things \
  -H "Content-Type: application/json" \
  -d '{
    "filter": "gt(features/temperature/properties/value,6)"
  }'
```

### Delete Thing

```bash
curl -X DELETE http://localhost:8080/api/2/things/org.eclipse.ditto:CS-01
```

## Ditto Query Language (RQL)

Ditto supports RQL (Resource Query Language) for searching:

### Operators

- `eq(field,value)` - Equals
- `ne(field,value)` - Not equals
- `gt(field,value)` - Greater than
- `lt(field,value)` - Less than
- `ge(field,value)` - Greater than or equal
- `le(field,value)` - Less than or equal
- `like(field,pattern)` - Pattern matching
- `exists(field)` - Field exists
- `and(expr1,expr2)` - Logical AND
- `or(expr1,expr2)` - Logical OR
- `not(expr)` - Logical NOT

### Query Examples

```bash
# Temperature above threshold
filter=gt(features/temperature/properties/value,8.0)

# Unhealthy units
filter=ne(features/status/properties/health,"healthy")

# Units with active alerts
filter=gt(features/status/properties/activeAlertCount,0)

# Specific location
filter=eq(attributes/location,"Warehouse A - Section 1")

# Complex query
filter=and(gt(features/temperature/properties/value,6),eq(features/compressor/properties/status,"ON"))
```

## Integration with Node-RED

Node-RED updates the digital twins in real-time:

1. **Receive MQTT message** from sensor
2. **Parse sensor data**
3. **Update Ditto Thing** via HTTP API
4. **Digital twin synchronized** with physical asset

### Example Node-RED HTTP Request

```javascript
// Prepare Ditto update payload
const unitId = msg.payload.unitId;
const thingId = `org.eclipse.ditto:${unitId}`;

const dittoUpdate = {
  features: {
    temperature: {
      properties: {
        value: msg.payload.temperature,
        status: msg.payload.temperature > 8 ? "critical" : 
                msg.payload.temperature > 6 ? "warning" : "normal",
        lastUpdated: msg.payload.timestamp
      }
    },
    humidity: {
      properties: {
        value: msg.payload.humidity,
        lastUpdated: msg.payload.timestamp
      }
    },
    compressor: {
      properties: {
        status: msg.payload.compressorStatus,
        lastUpdated: msg.payload.timestamp
      }
    },
    energy: {
      properties: {
        consumption: msg.payload.energyConsumption,
        lastUpdated: msg.payload.timestamp
      }
    }
  }
};

msg.url = `http://ditto-gateway:8080/api/2/things/${thingId}`;
msg.method = "PATCH";
msg.headers = {
  "Content-Type": "application/merge-patch+json"
};
msg.payload = dittoUpdate;

return msg;
```

## WebSocket API

Ditto supports WebSocket for real-time updates:

```javascript
const ws = new WebSocket('ws://localhost:8080/ws/2');

ws.onopen = () => {
  // Subscribe to changes for CS-01
  ws.send(JSON.stringify({
    topic: 'org.eclipse.ditto:CS-01/things/twin/commands/subscribe',
    headers: {},
    path: '/'
  }));
};

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  console.log('Thing updated:', message);
};
```

## Digital Twin vs Time-Series Data

Understanding the difference:

| Aspect | Digital Twin (Ditto) | Time-Series (InfluxDB) |
|--------|---------------------|------------------------|
| **Purpose** | Current state representation | Historical data storage |
| **Question** | What is the current state? | What happened over time? |
| **Updates** | Latest value overwrites | All values preserved |
| **Query** | "Get current temperature" | "Get temperature trend" |
| **Use Case** | Real-time monitoring, control | Analysis, trends, ML |
| **Storage** | Lightweight, single state | Heavy, all measurements |

## Initialization Script

Create a script to initialize all digital twins:

```bash
#!/bin/bash
# Initialize Ditto digital twins

DITTO_URL="http://localhost:8080/api/2"

echo "Creating policy..."
curl -X PUT ${DITTO_URL}/policies/org.eclipse.ditto:cold-storage-policy \
  -H "Content-Type: application/json" \
  -d @ditto/policies/cold-storage-policy.json

echo "Creating thing CS-01..."
curl -X PUT ${DITTO_URL}/things/org.eclipse.ditto:CS-01 \
  -H "Content-Type: application/json" \
  -d @ditto/things/CS-01.json

echo "Creating thing CS-02..."
curl -X PUT ${DITTO_URL}/things/org.eclipse.ditto:CS-02 \
  -H "Content-Type: application/json" \
  -d @ditto/things/CS-02.json

echo "Creating thing CS-03..."
curl -X PUT ${DITTO_URL}/things/org.eclipse.ditto:CS-03 \
  -H "Content-Type: application/json" \
  -d @ditto/things/CS-03.json

echo "Digital twins initialized successfully!"
```

## Troubleshooting

### Check Ditto Health

```bash
curl http://localhost:8080/health
```

### View Ditto Logs

```bash
docker-compose logs ditto-gateway
docker-compose logs ditto-things
docker-compose logs ditto-policies
```

### Verify MongoDB Connection

```bash
docker exec -it smart_cooling_mongodb mongo -u ditto -p ditto ditto --eval "db.things.count()"
```

### Reset Ditto Data

```bash
docker-compose down
docker volume rm smart_cooling_mongodb_data
docker-compose up -d
```

## Best Practices

1. **Use semantic naming**: Follow consistent namespace conventions
2. **Keep attributes static**: Use attributes for unchanging metadata
3. **Use features for state**: Dynamic data goes in features
4. **Update atomically**: Use PATCH for updating multiple properties
5. **Implement policies**: Control access appropriately
6. **Monitor performance**: Watch MongoDB and Ditto metrics
7. **Validate schemas**: Ensure consistent data structures
8. **Version definitions**: Use semantic versioning for Thing definitions

## References

- [Eclipse Ditto Documentation](https://eclipse.dev/ditto/)
- [Ditto HTTP API](https://eclipse.dev/ditto/http-api-doc.html)
- [Ditto Protocol](https://eclipse.dev/ditto/protocol-overview.html)
- [Thing Model](https://eclipse.dev/ditto/basic-thing.html)
