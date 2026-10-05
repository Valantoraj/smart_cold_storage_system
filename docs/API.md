# Smart Cold Storage Digital Twin - REST API Documentation

## Overview

The REST API provides programmatic access to the Smart Cold Storage Digital Twin system. It enables querying sensor data, accessing digital twin states, retrieving alerts, and obtaining predictive maintenance information.

**Base URL**: `http://localhost:3001/api`

**Format**: JSON

**Authentication**: None (for development - implement authentication for production)

## Quick Start

### Start the API Server

```bash
# Using Docker Compose (recommended)
docker-compose up -d api

# Or manually
cd api
npm install
npm start
```

### Test the API

```bash
# Health check
curl http://localhost:3001/api/health

# Get all storage units
curl http://localhost:3001/api/storage

# Get specific unit
curl http://localhost:3001/api/storage/CS-01
```

## Endpoints

### Health Check

#### GET /api/health

Check if the API server is running and connected to services.

**Response**:
```json
{
  "status": "healthy",
  "timestamp": "2026-10-05T10:30:00.000Z",
  "services": {
    "api": "running",
    "influxdb": "http://influxdb:8086",
    "ditto": "http://ditto-gateway:8080"
  }
}
```

---

## Storage Units

### GET /api/storage

List all cold storage units with basic status.

**Response**:
```json
{
  "count": 3,
  "units": [
    {
      "unitId": "CS-01",
      "location": "Warehouse A - Section 1",
      "status": "healthy",
      "temperature": 4.2,
      "lastUpdate": "2026-10-05T10:30:00Z"
    },
    {
      "unitId": "CS-02",
      "location": "Warehouse A - Section 2",
      "status": "attention",
      "temperature": 6.8,
      "lastUpdate": "2026-10-05T10:30:00Z"
    }
  ]
}
```

---

### GET /api/storage/:id

Get detailed information for a specific storage unit including all features from the digital twin.

**Parameters**:
- `id` (path): Storage unit ID (e.g., CS-01)

**Example**: `GET /api/storage/CS-01`

**Response**:
```json
{
  "unitId": "CS-01",
  "attributes": {
    "manufacturer": "ColdTech Industries",
    "model": "CT-5000",
    "location": "Warehouse A - Section 1",
    "capacity": "1000 cubic meters",
    "installDate": "2025-01-15"
  },
  "currentState": {
    "temperature": {
      "value": 4.2,
      "unit": "celsius",
      "status": "normal",
      "target": 4.0,
      "min": 2.0,
      "max": 6.0,
      "lastUpdated": "2026-10-05T10:30:00Z"
    },
    "humidity": {
      "value": 67.0,
      "unit": "percent",
      "status": "normal",
      "target": 65.0,
      "min": 50.0,
      "max": 80.0,
      "lastUpdated": "2026-10-05T10:30:00Z"
    },
    "compressor": {
      "status": "ON",
      "runtime": 3600,
      "cycles": 24,
      "health": "healthy",
      "lastUpdated": "2026-10-05T10:30:00Z"
    },
    "energy": {
      "consumption": 2.35,
      "unit": "kW",
      "efficiency": "normal",
      "lastUpdated": "2026-10-05T10:30:00Z"
    },
    "status": {
      "operational": true,
      "health": "healthy",
      "healthScore": 95,
      "lastMaintenance": "2026-08-15",
      "alerts": [],
      "activeAlertCount": 0
    },
    "maintenance": {
      "score": 23,
      "temperatureStability": 92.0,
      "energyEfficiency": 88.0,
      "compressorHealth": 95.0,
      "recommendation": "Normal operation",
      "priority": "low"
    }
  },
  "lastUpdate": "2026-10-05T10:30:00Z"
}
```

---

### GET /api/storage/:id/current

Get the most recent sensor readings for a storage unit.

**Parameters**:
- `id` (path): Storage unit ID

**Example**: `GET /api/storage/CS-01/current`

**Response**:
```json
{
  "unitId": "CS-01",
  "temperature": 4.2,
  "humidity": 67.0,
  "compressorStatus": "ON",
  "energyConsumption": 2.35,
  "timestamp": "2026-10-05T10:30:00Z"
}
```

---

### GET /api/storage/:id/history

Get historical sensor data for a storage unit.

**Parameters**:
- `id` (path): Storage unit ID
- `start` (query): Start time (default: -24h). Examples: -1h, -7d, 2026-10-01T00:00:00Z
- `end` (query): End time (default: now)
- `fields` (query): Comma-separated field list (default: temperature,humidity,energyConsumption)

**Example**: `GET /api/storage/CS-01/history?start=-6h&fields=temperature,energyConsumption`

**Response**:
```json
{
  "unitId": "CS-01",
  "timeRange": {
    "start": "-6h",
    "end": "now"
  },
  "count": 360,
  "data": [
    {
      "time": "2026-10-05T04:30:00Z",
      "unitId": "CS-01",
      "temperature": 4.1,
      "humidity": 66.5,
      "energyConsumption": 2.25,
      "compressorStatus": "OFF"
    },
    {
      "time": "2026-10-05T04:31:00Z",
      "unitId": "CS-01",
      "temperature": 4.2,
      "humidity": 66.7,
      "energyConsumption": 2.45,
      "compressorStatus": "ON"
    }
  ]
}
```

---

## Alerts

### GET /api/alerts

Get alerts across all storage units with optional filtering.

**Query Parameters**:
- `severity` (optional): Filter by severity (critical, warning, info)
- `status` (optional): Filter by status (active, resolved) - default: active
- `unitId` (optional): Filter by specific unit
- `start` (optional): Start time for query (default: -24h)

**Example**: `GET /api/alerts?severity=critical&status=active`

**Response**:
```json
{
  "count": 2,
  "filters": {
    "severity": "critical",
    "status": "active",
    "unitId": null
  },
  "alerts": [
    {
      "time": "2026-10-05T10:25:00Z",
      "unitId": "CS-02",
      "alertType": "temperature_critical_high",
      "severity": "critical",
      "message": "Temperature critically high: 9.5°C",
      "value": 9.5,
      "threshold": 10.0,
      "resolved": false
    },
    {
      "time": "2026-10-05T10:20:00Z",
      "unitId": "CS-03",
      "alertType": "energy_critical",
      "severity": "critical",
      "message": "Energy consumption critically high: 4.2kW",
      "value": 4.2,
      "threshold": 4.0,
      "resolved": false
    }
  ]
}
```

---

### GET /api/storage/:id/alerts

Get alerts for a specific storage unit.

**Parameters**:
- `id` (path): Storage unit ID
- `severity` (query): Filter by severity
- `status` (query): Filter by status (default: active)
- `start` (query): Start time (default: -24h)

**Example**: `GET /api/storage/CS-01/alerts?start=-1h`

**Response**: Same format as `/api/alerts` but filtered to the specific unit.

---

## Maintenance

### GET /api/maintenance/scores

Get predictive maintenance scores for all storage units.

**Response**:
```json
{
  "count": 3,
  "scores": [
    {
      "unitId": "CS-01",
      "score": 23,
      "temperatureStability": 92.0,
      "energyEfficiency": 88.0,
      "compressorHealth": 95.0,
      "recommendation": "Normal operation - routine maintenance only",
      "priority": "low",
      "lastCalculated": "2026-10-05T10:25:00Z"
    },
    {
      "unitId": "CS-02",
      "score": 67,
      "temperatureStability": 45.0,
      "energyEfficiency": 52.0,
      "compressorHealth": 68.0,
      "recommendation": "Schedule maintenance within 48 hours",
      "priority": "high",
      "lastCalculated": "2026-10-05T10:25:00Z"
    }
  ]
}
```

---

### GET /api/storage/:id/maintenance

Get predictive maintenance information for a specific unit.

**Parameters**:
- `id` (path): Storage unit ID

**Example**: `GET /api/storage/CS-02/maintenance`

**Response**:
```json
{
  "unitId": "CS-02",
  "score": 67,
  "temperatureStability": 45.0,
  "energyEfficiency": 52.0,
  "compressorHealth": 68.0,
  "recommendation": "Schedule maintenance within 48 hours",
  "priority": "high",
  "lastCalculated": "2026-10-05T10:25:00Z"
}
```

---

## Analytics

### GET /api/analytics/summary

Get system-wide analytics and statistics.

**Query Parameters**:
- `start` (optional): Start time for analysis (default: -24h)

**Example**: `GET /api/analytics/summary?start=-7d`

**Response**:
```json
{
  "timeRange": "-7d",
  "temperatures": [
    {
      "unitId": "CS-01",
      "avgTemperature": 4.15
    },
    {
      "unitId": "CS-02",
      "avgTemperature": 6.82
    },
    {
      "unitId": "CS-03",
      "avgTemperature": 4.28
    }
  ],
  "alerts": {
    "critical": 5,
    "warning": 23,
    "info": 12
  },
  "timestamp": "2026-10-05T10:30:00Z"
}
```

---

## Digital Twins

### GET /api/twins

List all digital twins (Things) in Eclipse Ditto.

**Response**:
```json
{
  "count": 3,
  "things": [
    {
      "thingId": "org.eclipse.ditto:CS-01",
      "policyId": "org.eclipse.ditto:cold-storage-policy",
      "attributes": { ... },
      "features": { ... }
    }
  ]
}
```

---

### GET /api/twins/:thingId

Get a specific digital twin by Thing ID.

**Parameters**:
- `thingId` (path): Full Thing ID (e.g., org.eclipse.ditto:CS-01)

**Example**: `GET /api/twins/org.eclipse.ditto:CS-01`

**Response**: Complete Thing JSON from Eclipse Ditto.

---

## Error Responses

All endpoints return standard error responses:

### 404 Not Found

```json
{
  "error": "Storage unit not found",
  "unitId": "CS-99"
}
```

### 500 Internal Server Error

```json
{
  "error": "Failed to fetch storage unit",
  "message": "Connection refused"
}
```

---

## Example Use Cases

### 1. Dashboard Integration

```javascript
// Fetch all units for dashboard
const response = await fetch('http://localhost:3001/api/storage');
const data = await response.json();

data.units.forEach(unit => {
  console.log(`${unit.unitId}: ${unit.temperature}°C - ${unit.status}`);
});
```

### 2. Temperature Monitoring

```javascript
// Get current temperature
const unit = 'CS-01';
const response = await fetch(`http://localhost:3001/api/storage/${unit}/current`);
const data = await response.json();

if (data.temperature > 8.0) {
  console.warn(`High temperature alert for ${unit}: ${data.temperature}°C`);
}
```

### 3. Historical Trend Analysis

```javascript
// Get 24-hour temperature history
const response = await fetch('http://localhost:3001/api/storage/CS-01/history?start=-24h&fields=temperature');
const data = await response.json();

const temps = data.data.map(d => d.temperature);
const avgTemp = temps.reduce((a, b) => a + b) / temps.length;
console.log(`24-hour average: ${avgTemp.toFixed(2)}°C`);
```

### 4. Alert Monitoring

```javascript
// Check for critical alerts
const response = await fetch('http://localhost:3001/api/alerts?severity=critical&status=active');
const data = await response.json();

if (data.count > 0) {
  console.error(`${data.count} critical alerts active!`);
  data.alerts.forEach(alert => {
    console.error(`${alert.unitId}: ${alert.message}`);
  });
}
```

### 5. Maintenance Priority

```javascript
// Get units needing maintenance
const response = await fetch('http://localhost:3001/api/maintenance/scores');
const data = await response.json();

const highPriority = data.scores.filter(s => s.priority === 'high' || s.priority === 'critical');

highPriority.forEach(unit => {
  console.log(`${unit.unitId}: Score ${unit.score} - ${unit.recommendation}`);
});
```

---

## Rate Limiting

Currently no rate limiting is implemented. For production:

- Implement rate limiting (e.g., 100 requests/minute per IP)
- Use API keys for authentication
- Add request logging and monitoring

---

## CORS

CORS is enabled for all origins in development. For production, configure specific allowed origins:

```javascript
app.use(cors({
  origin: ['https://dashboard.example.com', 'https://app.example.com']
}));
```

---

## Performance Tips

1. **Use time ranges**: Limit historical queries with appropriate `start` and `end` parameters
2. **Select specific fields**: Use the `fields` parameter to request only needed data
3. **Cache responses**: Implement caching for frequently accessed data
4. **Pagination**: For large result sets, implement pagination (future feature)
5. **WebSockets**: Consider WebSocket connections for real-time updates (future feature)

---

## Testing

### Manual Testing with cURL

```bash
# Health check
curl http://localhost:3001/api/health

# Get all units
curl http://localhost:3001/api/storage

# Get unit details with pretty JSON
curl http://localhost:3001/api/storage/CS-01 | json_pp

# Get history with parameters
curl "http://localhost:3001/api/storage/CS-01/history?start=-1h&fields=temperature"

# Get active alerts
curl http://localhost:3001/api/alerts?status=active

# Get maintenance scores
curl http://localhost:3001/api/maintenance/scores
```

### Automated Testing

See `tests/api_tests.sh` for automated test script.

---

## Future Enhancements

- **Authentication**: JWT-based authentication
- **Authorization**: Role-based access control
- **WebSockets**: Real-time data streaming
- **Pagination**: For large result sets
- **GraphQL**: Alternative query interface
- **OpenAPI/Swagger**: Interactive API documentation
- **Rate Limiting**: Request throttling
- **Caching**: Response caching for performance
- **Metrics**: API usage metrics and monitoring

---

## Support

For issues or questions:
1. Check logs: `docker logs smart_cooling_api`
2. Verify services are running: `docker ps`
3. Test connections to InfluxDB and Ditto
4. Review this documentation

---

**API Version**: 1.0.0  
**Last Updated**: 2026-10-05
