# Architecture Documentation

## Smart Cold Storage Digital Twin System

## Table of Contents
1. [System Architecture](#system-architecture)
2. [Component Details](#component-details)
3. [Data Flow](#data-flow)
4. [Digital Twin Concept](#digital-twin-concept)
5. [Abnormal Condition Detection](#abnormal-condition-detection)
6. [Predictive Maintenance](#predictive-maintenance)
7. [API Endpoints](#api-endpoints)

## System Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Physical Cold Storage Units                   │
│                     (CS-01, CS-02, CS-03, ...)                      │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  │ Sensor Data
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         MQTT Protocol Layer                          │
│                      (Mosquitto Broker - Port 1883)                 │
│          Topics: coldstorage/CS-01/data, coldstorage/CS-02/data     │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Node-RED Processing Layer                       │
│                           (Port 1880)                                │
│  ┌────────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────────┐  │
│  │   MQTT     │→ │  Parse   │→ │ Validate │→ │   Condition     │  │
│  │  Receive   │  │   Data   │  │   Data   │  │     Check       │  │
│  └────────────┘  └──────────┘  └──────────┘  └─────────────────┘  │
│                                       │                              │
│                         ┌─────────────┴─────────────┐               │
│                         ▼                           ▼               │
│              ┌───────────────────┐      ┌──────────────────┐       │
│              │  Write to         │      │  Update Digital  │       │
│              │  InfluxDB         │      │  Twin (Ditto)    │       │
│              └───────────────────┘      └──────────────────┘       │
│                         │                           │               │
└─────────────────────────┼───────────────────────────┼───────────────┘
                          │                           │
            ┌─────────────┴──────┐        ┌──────────┴──────────┐
            ▼                    ▼        ▼                      ▼
┌──────────────────┐  ┌──────────────────────┐  ┌────────────────────┐
│    InfluxDB      │  │   Eclipse Ditto      │  │   Alert System     │
│  Time-Series DB  │  │  Digital Twin State  │  │   Notifications    │
│   (Port 8086)    │  │   (Port 8080)        │  │                    │
└──────────────────┘  └──────────────────────┘  └────────────────────┘
            │                    │
            └────────┬───────────┘
                     ▼
         ┌────────────────────────┐
         │   Grafana Dashboard    │
         │   Visualization        │
         │     (Port 3000)        │
         └────────────────────────┘
                     │
                     ▼
         ┌────────────────────────┐
         │  Operators/Users       │
         │  Monitoring Interface  │
         └────────────────────────┘
```

## Component Details

### 1. MQTT and Mosquitto

**Purpose**: Lightweight communication protocol for IoT sensor data transmission.

**Configuration**:
- Port: 1883 (MQTT)
- Port: 9001 (WebSocket, optional)
- Protocol: MQTT v3.1.1 / v5.0

**Topic Structure**:
```
coldstorage/CS-01/data
coldstorage/CS-02/data
coldstorage/CS-03/data
```

**Message Payload Format** (JSON):
```json
{
  "unitId": "CS-01",
  "temperature": 4.2,
  "humidity": 67,
  "compressorStatus": "ON",
  "energyConsumption": 2.3,
  "timestamp": "2026-09-30T10:30:00Z"
}
```

### 2. Node-RED

**Purpose**: Data processing, orchestration, and business logic implementation.

**Port**: 1880

**Main Flows**:
1. **MQTT Input Flow**: Subscribes to all cold storage topics
2. **Data Validation Flow**: Validates incoming sensor data
3. **InfluxDB Writer Flow**: Stores time-series data
4. **Ditto Updater Flow**: Updates digital twin state
5. **Condition Detection Flow**: Identifies abnormal conditions
6. **Alert Flow**: Generates and sends notifications

**Key Functions**:
- Parse and validate MQTT messages
- Route data to appropriate storage systems
- Execute condition-checking logic
- Trigger alerts based on rules
- Maintain data consistency

### 3. InfluxDB

**Purpose**: Time-series database for historical sensor data storage and analysis.

**Port**: 8086

**Database Structure**:
- **Bucket**: `cold_storage`
- **Organization**: `smart_cooling`
- **Retention**: 90 days (configurable)

**Measurements**:
```
measurement: sensor_data
tags:
  - unitId (CS-01, CS-02, etc.)
  - location (optional)
fields:
  - temperature (float)
  - humidity (float)
  - energyConsumption (float)
  - compressorStatus (string)
timestamp: RFC3339
```

**Query Example**:
```flux
from(bucket: "cold_storage")
  |> range(start: -24h)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> filter(fn: (r) => r["unitId"] == "CS-01")
  |> filter(fn: (r) => r["_field"] == "temperature")
```

### 4. Eclipse Ditto

**Purpose**: Digital twin platform for managing current state of physical assets.

**Port**: 8080

**API Version**: v2

**Thing Model Structure**:
```json
{
  "thingId": "org.eclipse.ditto:CS-01",
  "policyId": "org.eclipse.ditto:cold-storage-policy",
  "attributes": {
    "location": "Warehouse A",
    "capacity": "1000 cubic meters",
    "installDate": "2025-01-15"
  },
  "features": {
    "temperature": {
      "properties": {
        "value": 4.2,
        "unit": "celsius",
        "status": "normal"
      }
    },
    "humidity": {
      "properties": {
        "value": 67,
        "unit": "percent",
        "status": "normal"
      }
    },
    "compressor": {
      "properties": {
        "status": "ON",
        "runtime": 3600,
        "cycles": 24
      }
    },
    "energy": {
      "properties": {
        "consumption": 2.3,
        "unit": "kW",
        "efficiency": "normal"
      }
    },
    "status": {
      "properties": {
        "operational": true,
        "health": "healthy",
        "lastMaintenance": "2026-08-15",
        "alerts": []
      }
    }
  }
}
```

### 5. Grafana

**Purpose**: Visualization, monitoring, and alerting interface.

**Port**: 3000

**Dashboards**:
1. **Overview Dashboard**: All storage units at a glance
2. **Unit Detail Dashboard**: Deep dive into specific unit
3. **Trend Analysis Dashboard**: Historical patterns
4. **Alert Dashboard**: Current and past alerts
5. **Predictive Maintenance Dashboard**: Risk indicators

**Data Sources**:
- InfluxDB (primary time-series data)
- Eclipse Ditto (via REST API for current state)

### 6. REST API

**Purpose**: Programmatic access to system functions and data.

**Port**: 3001

**Endpoints**:
```
GET  /api/storage               - List all storage units
GET  /api/storage/:id           - Get specific unit details
GET  /api/storage/:id/history   - Get historical data
GET  /api/storage/:id/alerts    - Get alerts for unit
POST /api/storage/:id/alerts    - Create alert
GET  /api/health                - System health check
GET  /api/twins                 - List all digital twins
```

## Data Flow

### Normal Operation Flow

```
1. Physical Sensor Measurement
   └─> Temperature: 4.2°C, Humidity: 67%, Compressor: ON, Energy: 2.3kW

2. MQTT Publish
   └─> Topic: coldstorage/CS-01/data
   └─> Payload: JSON sensor data

3. Mosquitto Broker
   └─> Receives and queues message
   └─> Forwards to subscribers

4. Node-RED Processing
   ├─> Parse JSON payload
   ├─> Validate data (range checks, type validation)
   ├─> Extract unitId and timestamp
   └─> Route to storage and twin update

5. Parallel Storage
   ├─> InfluxDB: Write time-series record
   │   └─> Bucket: cold_storage
   │   └─> Measurement: sensor_data
   │   └─> Tags: unitId=CS-01
   │
   └─> Eclipse Ditto: Update digital twin
       └─> Thing: org.eclipse.ditto:CS-01
       └─> Update all feature properties

6. Condition Check
   ├─> Compare against thresholds
   ├─> Analyze recent trends
   └─> Evaluate multi-signal patterns

7. Visualization
   └─> Grafana queries InfluxDB and Ditto
   └─> Updates dashboards in real-time
```

### Abnormal Condition Flow

```
1. Detect Anomaly
   └─> Temperature increasing: 4.0 → 4.5 → 5.2 → 6.1 → 7.0°C
   └─> Compressor runtime increasing
   └─> Energy consumption increasing

2. Condition Evaluation
   └─> Node-RED runs detection logic
   └─> Multiple conditions trigger

3. Alert Generation
   ├─> Create alert record
   ├─> Update digital twin status
   └─> Store in InfluxDB

4. Notification
   ├─> Display in Grafana
   ├─> Log to system
   └─> Optional: Email/SMS (configurable)

5. Operator Action
   └─> Review dashboard
   └─> Investigate equipment
   └─> Perform maintenance
```

## Digital Twin Concept

### What is a Digital Twin?

A digital twin is a virtual representation of a physical object or system that:
- **Mirrors the physical state** continuously
- **Updates in real-time** as sensor data arrives
- **Maintains current state** separate from historical data
- **Provides a single source of truth** for the asset's condition

### Physical vs Digital

```
┌────────────────────────┐         ┌────────────────────────┐
│   Physical Asset       │         │   Digital Twin         │
│   (CS-01 Storage)      │  ←───→  │   (Ditto Thing)        │
│                        │         │                        │
│  Temperature: 4.2°C    │  sync   │  Temperature: 4.2°C    │
│  Humidity: 67%         │  ←───→  │  Humidity: 67%         │
│  Compressor: ON        │         │  Compressor: ON        │
│  Energy: 2.3kW         │         │  Energy: 2.3kW         │
└────────────────────────┘         └────────────────────────┘
```

### Why Separate InfluxDB and Ditto?

| Aspect | InfluxDB | Eclipse Ditto |
|--------|----------|---------------|
| **Purpose** | Historical analysis | Current state representation |
| **Question** | What happened over time? | What is happening now? |
| **Data Type** | Time-series sequences | Latest state snapshot |
| **Use Case** | Trend analysis, anomaly detection | Real-time monitoring, twin queries |
| **Query** | "Show temperature for last 24h" | "What is current temperature?" |

## Abnormal Condition Detection

### Detection Levels

#### Level 1: Threshold-Based Detection

Simple rule-based checks on individual measurements:

```javascript
// Temperature threshold
if (temperature > TEMP_THRESHOLD_HIGH) {
  generateAlert("Temperature too high", "warning");
}

if (temperature < TEMP_THRESHOLD_LOW) {
  generateAlert("Temperature too low", "warning");
}

// Humidity threshold
if (humidity > HUMIDITY_THRESHOLD_HIGH || humidity < HUMIDITY_THRESHOLD_LOW) {
  generateAlert("Humidity out of range", "warning");
}

// Energy consumption
if (energyConsumption > ENERGY_THRESHOLD) {
  generateAlert("High energy consumption", "info");
}
```

#### Level 2: Trend-Based Detection

Analyzes patterns over time windows:

```javascript
// Get last 10 temperature readings
const recentTemps = getRecentData(unitId, "temperature", 10);

// Check for continuously increasing trend
const isIncreasing = recentTemps.every((val, idx) => 
  idx === 0 || val >= recentTemps[idx - 1]
);

if (isIncreasing && temperatureDelta > TREND_THRESHOLD) {
  generateAlert("Temperature rising trend detected", "warning");
}
```

#### Level 3: Multi-Signal Pattern Detection

Combines multiple indicators for sophisticated detection:

```javascript
// Predictive maintenance pattern
const tempIncreasing = analyzeTemperatureTrend(unitId);
const compressorRuntimeHigh = analyzeCompressorRuntime(unitId);
const energyIncreasing = analyzeEnergyTrend(unitId);

if (tempIncreasing && compressorRuntimeHigh && energyIncreasing) {
  generateAlert("Potential equipment degradation", "critical");
  createMaintenanceTicket(unitId);
}
```

### Thresholds Configuration

```javascript
const THRESHOLDS = {
  temperature: {
    critical_high: 10.0,  // °C
    warning_high: 8.0,
    normal_high: 6.0,
    normal_low: 2.0,
    warning_low: 0.0,
    critical_low: -2.0
  },
  humidity: {
    high: 80,  // %
    low: 50
  },
  energy: {
    warning: 3.0,  // kW
    critical: 4.0
  },
  compressor: {
    max_runtime: 3600,  // seconds
    max_cycles_per_hour: 10
  }
};
```

## Predictive Maintenance

### Rule-Based Approach

#### Pattern 1: Inefficient Cooling

```
Condition:
  - Temperature increasing over 6 consecutive measurements
  - Compressor status = ON continuously
  - Energy consumption > normal baseline + 20%

Interpretation:
  - Cooling system losing efficiency
  - Possible refrigerant leak
  - Possible compressor wear

Action:
  - Generate predictive maintenance alert
  - Schedule inspection within 48 hours
```

#### Pattern 2: Excessive Cycling

```
Condition:
  - Compressor ON/OFF cycles > 15 per hour
  - Temperature fluctuating ±1°C around setpoint
  - Energy consumption normal

Interpretation:
  - Thermostat issue
  - Door seal problem
  - Possible control system malfunction

Action:
  - Generate maintenance alert
  - Check door seals and controls
```

#### Pattern 3: Energy Inefficiency

```
Condition:
  - Energy consumption increasing over 7 days
  - Temperature maintained within normal range
  - Compressor runtime increasing

Interpretation:
  - System working harder to maintain temperature
  - Possible condenser coil dirt buildup
  - Possible airflow restriction

Action:
  - Schedule cleaning and inspection
  - Monitor for further degradation
```

### Predictive Maintenance Score

```javascript
function calculateMaintenanceScore(unitId) {
  let score = 0;
  
  // Temperature stability (0-30 points)
  score += analyzeTemperatureStability(unitId);
  
  // Energy efficiency (0-30 points)
  score += analyzeEnergyEfficiency(unitId);
  
  // Compressor health (0-40 points)
  score += analyzeCompressorHealth(unitId);
  
  // Score interpretation:
  // 0-20: Healthy - routine maintenance only
  // 21-50: Monitor - watch for trends
  // 51-70: Attention needed - schedule inspection
  // 71-100: Critical - immediate maintenance required
  
  return score;
}
```

## API Endpoints

### Complete API Reference

#### Storage Unit Endpoints

```
GET /api/storage
Description: List all storage units
Response: Array of unit summaries

GET /api/storage/:id
Description: Get detailed information for specific unit
Response: Unit details including current state and digital twin

GET /api/storage/:id/history
Parameters: 
  - start: ISO timestamp (default: -24h)
  - end: ISO timestamp (default: now)
  - fields: comma-separated list (default: all)
Response: Time-series data array

GET /api/storage/:id/alerts
Parameters:
  - severity: critical|warning|info
  - status: active|resolved
Response: Array of alerts

POST /api/storage/:id/alerts
Body: Alert details
Response: Created alert

GET /api/storage/:id/maintenance-score
Response: Predictive maintenance score (0-100)
```

#### Digital Twin Endpoints

```
GET /api/twins
Description: List all digital twins
Response: Array of Thing IDs

GET /api/twins/:thingId
Description: Get complete Thing definition
Response: Full Thing JSON

PATCH /api/twins/:thingId
Description: Update Thing properties
Body: JSON patch
Response: Updated Thing
```

#### System Endpoints

```
GET /api/health
Description: System health check
Response: Status of all components

GET /api/metrics
Description: System-wide metrics
Response: Performance and usage metrics
```

## Security Considerations

### Authentication & Authorization

- Grafana: Username/password authentication
- Eclipse Ditto: Policy-based access control
- API: API key or JWT tokens (to be implemented)
- MQTT: Optional username/password (configurable)

### Network Security

- Internal Docker network for inter-container communication
- Exposed ports only for necessary services
- Optional TLS/SSL for MQTT and HTTP

### Data Privacy

- Sensor data contains no personally identifiable information
- Access logs maintained for audit
- Data retention policies configurable

## Scalability Considerations

### Horizontal Scaling

- **Node-RED**: Can run multiple instances with MQTT load balancing
- **InfluxDB**: Supports clustering for large deployments
- **Eclipse Ditto**: Built for horizontal scaling
- **Mosquitto**: Can use clustering or bridge mode

### Performance Optimization

- MQTT QoS level 1 for reliable delivery without overhead
- InfluxDB downsampling for long-term storage
- Grafana query caching for dashboard performance
- Node-RED flow optimization for minimal latency

## Maintenance and Operations

### Monitoring

- Docker container health checks
- Service availability monitoring
- Data pipeline flow verification
- Alert delivery confirmation

### Backup and Recovery

- InfluxDB automated backups
- Eclipse Ditto state snapshots
- Node-RED flow version control
- Grafana dashboard exports

### Updates and Upgrades

- Rolling updates for services
- Configuration version control
- Testing in staging environment
- Rollback procedures

---

**Document Version**: 1.0  
**Last Updated**: 2026-10-05  
**Next Review**: 2026-11-05
