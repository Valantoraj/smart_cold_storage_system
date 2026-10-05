# Predictive Maintenance System

## Overview

The predictive maintenance system analyzes multiple signals from cold storage units to detect developing equipment problems before they become failures. Unlike simple threshold alerts, predictive maintenance combines temperature trends, energy consumption patterns, and compressor behavior to identify subtle signs of degradation.

## Core Concept

**Traditional Monitoring**: "Temperature is 9°C - ALERT!"  
**Predictive Maintenance**: "Temperature rising + energy increasing + compressor running longer = equipment degradation likely in next 48 hours"

## How It Works

### 1. Multi-Signal Analysis

The system analyzes three key indicators:

#### Temperature Stability (35% weight)
- **Metric**: Temperature variance and trend over time
- **Good**: Stable temperature with small fluctuations
- **Bad**: Increasing temperature despite compressor running
- **Score**: 0-100 (100 = perfectly stable)

**Indicators**:
- Standard deviation of temperature readings
- Rising trend over last hour
- Ability to maintain target temperature

#### Energy Efficiency (35% weight)
- **Metric**: Energy consumption trend and baseline deviation
- **Good**: Stable energy consumption around 2-2.5 kW
- **Bad**: Increasing energy despite maintaining temperature
- **Score**: 0-100 (100 = optimal efficiency)

**Indicators**:
- Average energy consumption
- Energy consumption trend
- Energy per degree of cooling

#### Compressor Health (30% weight)
- **Metric**: Compressor runtime percentage and cycling
- **Good**: 40-60% runtime with regular cycles
- **Bad**: >70% runtime or <30% runtime
- **Score**: 0-100 (100 = optimal operation)

**Indicators**:
- Percentage of time compressor is ON
- Frequency of ON/OFF cycles
- Runtime duration patterns

### 2. Maintenance Score Calculation

```
Maintenance Score = 
  (100 - Temperature Stability) × 0.35 +
  (100 - Energy Efficiency) × 0.35 +
  (100 - Compressor Health) × 0.30
```

**Score ranges**:
- **0-20**: Normal - Routine maintenance only
- **21-40**: Monitor - Watch trends
- **41-60**: Medium - Schedule inspection within 2 weeks
- **61-80**: High - Schedule maintenance within 48 hours
- **81-100**: Critical - Immediate maintenance required

### 3. Pattern Recognition

The system identifies specific degradation patterns:

#### Pattern 1: Inefficient Cooling
```
Temperature: Rising trend
Compressor: Running longer
Energy: Increasing
→ Possible refrigerant leak or compressor wear
```

#### Pattern 2: Control System Issues
```
Temperature: Highly variable
Compressor: Excessive cycling
Energy: Variable
→ Possible thermostat or control malfunction
```

#### Pattern 3: Energy Inefficiency
```
Temperature: Normal
Compressor: Normal runtime
Energy: Significantly elevated
→ Possible condenser coil buildup or airflow restriction
```

#### Pattern 4: Equipment Degradation
```
Temperature: Gradually rising
Compressor: Increasing runtime
Energy: Gradually increasing
→ General equipment degradation, multiple components affected
```

## Implementation

### Node-RED Flow Architecture

```
Timer (Every 5 min)
    ↓
Get Unit List
    ↓
┌───────────────┬─────────────────┬────────────────────┐
│               │                 │                    │
Query Temp    Query Energy    Query Compressor
Trend         Trend           Runtime
│               │                 │
└───────────────┴─────────────────┴────────────────────┘
                        ↓
            Aggregate Analysis Results
                        ↓
         Calculate Maintenance Score
                        ↓
        ┌───────────────┴────────────────┐
        ↓                                 ↓
Update Ditto                    Check Threshold
Maintenance Feature             (Score >= 60)
                                        ↓
                                ┌───────┴────────┐
                                ↓                ↓
                        Publish MQTT      Write InfluxDB
                        Alert            Analytics
```

### InfluxDB Queries

#### Temperature Trend Query

```flux
from(bucket: "cold_storage")
  |> range(start: -1h)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> filter(fn: (r) => r["unitId"] == "CS-01")
  |> filter(fn: (r) => r["_field"] == "temperature")
  |> derivative(unit: 1h, nonNegative: false)
  |> mean()
```

**Returns**: Average rate of temperature change per hour

#### Energy Trend Query

```flux
from(bucket: "cold_storage")
  |> range(start: -1h)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> filter(fn: (r) => r["unitId"] == "CS-01")
  |> filter(fn: (r) => r["_field"] == "energyConsumption")
  |> derivative(unit: 1h, nonNegative: false)
  |> mean()
```

**Returns**: Average rate of energy change per hour

#### Compressor Runtime Query

```flux
import "strings"

data = from(bucket: "cold_storage")
  |> range(start: -1h)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> filter(fn: (r) => r["unitId"] == "CS-01")
  |> filter(fn: (r) => r["_field"] == "compressorStatus")

total = data |> count() |> findRecord(fn: (key) => true, idx: 0)

on_count = data 
  |> filter(fn: (r) => r["_value"] == "ON")
  |> count()
  |> findRecord(fn: (key) => true, idx: 0)

data
  |> limit(n: 1)
  |> map(fn: (r) => ({
      _value: float(v: on_count._value) / float(v: total._value) * 100.0
  }))
```

**Returns**: Percentage of time compressor was ON

### Ditto Digital Twin Update

The maintenance score is stored in the Thing's maintenance feature:

```json
{
  "features": {
    "maintenance": {
      "properties": {
        "score": 45,
        "temperatureStability": 85.0,
        "energyEfficiency": 78.0,
        "compressorHealth": 92.0,
        "recommendation": "Schedule inspection within 2 weeks",
        "priority": "medium",
        "lastCalculated": "2026-10-05T10:30:00Z"
      }
    },
    "status": {
      "properties": {
        "healthScore": 85,
        "health": "attention"
      }
    }
  }
}
```

### Alert Generation

When maintenance score >= 60, an alert is published:

```json
{
  "unitId": "CS-02",
  "alertType": "predictive_maintenance",
  "severity": "warning",
  "message": "Predictive maintenance alert: Schedule maintenance within 48 hours",
  "maintenanceScore": 67,
  "details": {
    "temperatureTrend": "increasing",
    "energyTrend": "increasing",
    "compressorRuntime": "72%",
    "averageTemperature": 5.8,
    "averageEnergy": 2.9
  },
  "timestamp": "2026-10-05T10:30:00Z"
}
```

## Configuration

### Analysis Interval

Default: Every 5 minutes

Adjust in Node-RED inject node:
```javascript
{
  "repeat": "300",  // 300 seconds = 5 minutes
  "once": true,     // Run once at startup
  "onceDelay": "10" // Wait 10 seconds after startup
}
```

### Thresholds

Modify in the "Calculate Maintenance Score" function:

```javascript
// Score interpretation
if (maintenanceScore < 20) {
    priority = 'low';
    recommendation = 'Normal operation - routine maintenance only';
} else if (maintenanceScore < 40) {
    priority = 'low';
    recommendation = 'Monitor trends - no immediate action needed';
} else if (maintenanceScore < 60) {
    priority = 'medium';
    recommendation = 'Schedule inspection within 2 weeks';
} else if (maintenanceScore < 80) {
    priority = 'high';
    recommendation = 'Schedule maintenance within 48 hours';
} else {
    priority = 'critical';
    recommendation = 'Immediate maintenance required';
}
```

### Weights

Adjust component weights in the calculation:

```javascript
const maintenanceScore = Math.round(
    (100 - tempStabilityScore) * 0.35 +      // Temperature: 35%
    (100 - energyEfficiencyScore) * 0.35 +   // Energy: 35%
    (100 - compressorHealthScore) * 0.30     // Compressor: 30%
);
```

## Testing Scenarios

### Scenario 1: Normal Operation

```bash
python sensor_simulator.py --units CS-01:normal --interval 30 --duration 1800
```

**Expected**:
- Maintenance score: 10-25
- Priority: low
- No predictive maintenance alerts
- All component scores > 80

### Scenario 2: Equipment Degradation

```bash
python sensor_simulator.py --units CS-02:equipment_degradation --interval 30 --duration 1800
```

**Expected**:
- Maintenance score increases over time: 30 → 50 → 70
- Priority escalates: low → medium → high
- Predictive maintenance alert after ~15-20 minutes
- All three component scores declining

### Scenario 3: Temperature Rising

```bash
python sensor_simulator.py --units CS-03:temp_rising --interval 20 --duration 1200
```

**Expected**:
- Temperature stability score decreases rapidly
- Energy efficiency also declines
- Maintenance score: 50-70
- Alert: "Schedule maintenance within 48 hours"

### Scenario 4: High Energy Only

```bash
python sensor_simulator.py --units CS-01:high_energy --interval 30 --duration 1200
```

**Expected**:
- Energy efficiency score low (40-60)
- Temperature stability remains high
- Compressor health remains high
- Maintenance score: 30-45 (medium priority)

## Monitoring

### View Maintenance Scores

```bash
# Get maintenance feature from Ditto
curl http://localhost:8080/api/2/things/org.eclipse.ditto:CS-01/features/maintenance

# Query maintenance scores from InfluxDB
curl -XPOST 'http://localhost:8086/api/v2/query?org=smart_cooling' \
  --header 'Authorization: Token smart-cooling-super-secret-token' \
  --header 'Content-Type: application/vnd.flux' \
  --data 'from(bucket:"analytics") |> range(start: -24h) |> filter(fn: (r) => r["_measurement"] == "maintenance_score")'
```

### Dashboard Visualization

Create a Grafana panel showing:
- Maintenance score over time (line chart)
- Component scores (temperature, energy, compressor) as gauges
- Current priority and recommendation (stat panel)
- Alert history (table)

### Subscribe to Maintenance Alerts

```bash
docker exec -it smart_cooling_mosquitto mosquitto_sub -t "coldstorage/+/alerts" -v | grep predictive_maintenance
```

## Benefits

### Early Problem Detection

- **Detection Window**: 6-48 hours before failure
- **False Positive Rate**: Low (requires multiple signals)
- **Actionable Insights**: Specific recommendations

### Cost Savings

- **Prevent Failures**: Avoid food spoilage and emergency repairs
- **Optimize Maintenance**: Schedule during planned downtime
- **Extend Equipment Life**: Address issues before they cause damage

### Operational Efficiency

- **Automated Analysis**: No manual trend monitoring needed
- **Prioritized Actions**: Focus on high-risk units first
- **Data-Driven Decisions**: Objective maintenance scheduling

## Advanced Features

### Machine Learning Integration (Future)

The current rule-based system can be enhanced with ML:

1. **Anomaly Detection**: Use statistical models to identify unusual patterns
2. **Failure Prediction**: Train models on historical failure data
3. **Remaining Useful Life**: Estimate time until maintenance needed
4. **Root Cause Analysis**: Identify specific component failures

### Example ML Approach

```python
# Pseudocode for ML-enhanced predictive maintenance

from sklearn.ensemble import RandomForestClassifier
import pandas as pd

# Feature engineering
features = [
    'temperature_mean',
    'temperature_std',
    'temperature_trend',
    'energy_mean',
    'energy_trend',
    'compressor_runtime_pct',
    'compressor_cycles_per_hour'
]

# Train model on historical data
model = RandomForestClassifier()
model.fit(historical_features, failure_labels)

# Predict maintenance need
maintenance_probability = model.predict_proba(current_features)
```

### Multi-Unit Correlation

Analyze patterns across multiple units:
- Compare units in same facility
- Identify facility-wide issues
- Detect environmental factors

### Seasonal Adjustments

Adjust thresholds based on:
- Ambient temperature
- Facility load
- Time of year
- Operating conditions

## Troubleshooting

### High False Positive Rate

**Problem**: Too many alerts for normal conditions

**Solutions**:
1. Increase alert threshold (e.g., 60 → 70)
2. Require sustained high score (2-3 consecutive analyses)
3. Adjust component score calculations
4. Filter out transient spikes

### Missed Failures

**Problem**: Failures occurring without alerts

**Solutions**:
1. Decrease alert threshold
2. Add more signals (door status, ambient temp)
3. Reduce analysis interval (5 min → 2 min)
4. Review score calculation weights

### Delayed Detection

**Problem**: Alerts come too late

**Solutions**:
1. Use shorter time windows for trend analysis
2. Weight recent data more heavily
3. Add derivative of trends (acceleration)
4. Reduce analysis interval

## Best Practices

1. **Validate with Historical Data**: Test against known failures
2. **Tune Thresholds**: Adjust based on equipment and facility
3. **Regular Review**: Periodically review alert accuracy
4. **Action Tracking**: Log maintenance actions and outcomes
5. **Continuous Improvement**: Refine based on experience

## References

- Predictive Maintenance with IoT: Best Practices
- Condition-Based Monitoring for Industrial Equipment
- Multi-Signal Fault Detection Algorithms
- InfluxDB Time-Series Analysis
- Eclipse Ditto Digital Twin Patterns
