# InfluxDB Configuration and Schema

## Overview

InfluxDB is used as the time-series database for storing historical sensor measurements from all cold storage units.

## Database Structure

### Organization
- **Name**: `smart_cooling`
- **Description**: Smart Cold Storage Digital Twin system organization

### Buckets

| Bucket Name | Retention | Purpose |
|------------|-----------|---------|
| `cold_storage` | 90 days | Primary sensor data storage |
| `alerts` | 365 days | Alert and notification history |
| `analytics` | 730 days | Aggregated analytics data |
| `cold_storage_downsampled` | 1825 days (5 years) | Downsampled long-term data |

## Data Schema

### Measurement: sensor_data

Primary measurement for all sensor readings from cold storage units.

**Tags** (indexed for fast queries):
- `unitId`: Storage unit identifier (CS-01, CS-02, etc.)
- `location`: Physical location (optional)
- `building`: Building identifier (optional)

**Fields** (actual values):
- `temperature`: Temperature in Celsius (float)
- `humidity`: Humidity percentage (float)
- `compressorStatus`: ON/OFF (string)
- `energyConsumption`: Energy consumption in kW (float)

**Timestamp**: RFC3339 format (automatically indexed)

### Example Data Point

```
sensor_data,unitId=CS-01,location=WarehouseA temperature=4.2,humidity=67,compressorStatus="ON",energyConsumption=2.3 1696507800000000000
```

JSON representation:
```json
{
  "measurement": "sensor_data",
  "tags": {
    "unitId": "CS-01",
    "location": "WarehouseA"
  },
  "fields": {
    "temperature": 4.2,
    "humidity": 67,
    "compressorStatus": "ON",
    "energyConsumption": 2.3
  },
  "timestamp": "2026-10-05T10:30:00Z"
}
```

### Measurement: alerts

Stores alert and notification history.

**Tags**:
- `unitId`: Storage unit identifier
- `alertType`: Type of alert (temperature_high, humidity_out_of_range, etc.)
- `severity`: critical, warning, info

**Fields**:
- `message`: Alert message (string)
- `value`: Current value that triggered alert (float)
- `threshold`: Threshold that was exceeded (float)
- `resolved`: Whether alert is resolved (boolean)

**Timestamp**: When the alert was generated

### Measurement: compressor_metrics

Detailed compressor performance metrics.

**Tags**:
- `unitId`: Storage unit identifier

**Fields**:
- `runtime`: Total runtime in seconds (integer)
- `cycles`: Number of ON/OFF cycles (integer)
- `efficiency`: Calculated efficiency percentage (float)
- `avgCycleTime`: Average cycle time (float)

### Measurement: maintenance_score

Predictive maintenance scores calculated by the system.

**Tags**:
- `unitId`: Storage unit identifier

**Fields**:
- `score`: Maintenance score 0-100 (integer)
- `temperatureStability`: Temperature stability score (float)
- `energyEfficiency`: Energy efficiency score (float)
- `compressorHealth`: Compressor health score (float)
- `recommendation`: Maintenance recommendation (string)

## Flux Query Examples

### Get Last 24 Hours of Temperature Data

```flux
from(bucket: "cold_storage")
  |> range(start: -24h)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> filter(fn: (r) => r["unitId"] == "CS-01")
  |> filter(fn: (r) => r["_field"] == "temperature")
  |> yield(name: "temperature")
```

### Get Average Temperature Per Hour

```flux
from(bucket: "cold_storage")
  |> range(start: -7d)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> filter(fn: (r) => r["unitId"] == "CS-01")
  |> filter(fn: (r) => r["_field"] == "temperature")
  |> aggregateWindow(every: 1h, fn: mean, createEmpty: false)
  |> yield(name: "hourly_avg_temp")
```

### Get All Units Current Status

```flux
from(bucket: "cold_storage")
  |> range(start: -5m)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> last()
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> yield(name: "current_status")
```

### Detect Temperature Rising Trend

```flux
from(bucket: "cold_storage")
  |> range(start: -1h)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> filter(fn: (r) => r["unitId"] == "CS-01")
  |> filter(fn: (r) => r["_field"] == "temperature")
  |> derivative(unit: 1m, nonNegative: false)
  |> filter(fn: (r) => r["_value"] > 0.1)
  |> yield(name: "rising_trend")
```

### Get Compressor Runtime

```flux
from(bucket: "cold_storage")
  |> range(start: -24h)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> filter(fn: (r) => r["unitId"] == "CS-01")
  |> filter(fn: (r) => r["_field"] == "compressorStatus")
  |> map(fn: (r) => ({ r with _value: if r._value == "ON" then 1 else 0 }))
  |> sum()
  |> yield(name: "compressor_on_count")
```

### Get Energy Consumption Stats

```flux
from(bucket: "cold_storage")
  |> range(start: -24h)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> filter(fn: (r) => r["_field"] == "energyConsumption")
  |> group(columns: ["unitId"])
  |> mean()
  |> yield(name: "avg_energy")
```

### Get Recent Alerts

```flux
from(bucket: "alerts")
  |> range(start: -24h)
  |> filter(fn: (r) => r["_measurement"] == "alerts")
  |> filter(fn: (r) => r["unitId"] == "CS-01")
  |> filter(fn: (r) => r["resolved"] == false)
  |> sort(columns: ["_time"], desc: true)
  |> yield(name: "active_alerts")
```

### Compare Multiple Units

```flux
from(bucket: "cold_storage")
  |> range(start: -24h)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> filter(fn: (r) => r["_field"] == "temperature")
  |> aggregateWindow(every: 1h, fn: mean, createEmpty: false)
  |> pivot(rowKey: ["_time"], columnKey: ["unitId"], valueColumn: "_value")
  |> yield(name: "unit_comparison")
```

### Anomaly Detection (Statistical)

```flux
import "contrib/tomhollingworth/events"

data = from(bucket: "cold_storage")
  |> range(start: -7d)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> filter(fn: (r) => r["unitId"] == "CS-01")
  |> filter(fn: (r) => r["_field"] == "temperature")

mean_val = data
  |> mean()
  |> findRecord(fn: (key) => true, idx: 0)

stddev_val = data
  |> stddev()
  |> findRecord(fn: (key) => true, idx: 0)

data
  |> map(fn: (r) => ({
      r with
      zscore: (r._value - mean_val._value) / stddev_val._value,
      is_anomaly: if (r._value - mean_val._value) / stddev_val._value > 2.0 or (r._value - mean_val._value) / stddev_val._value < -2.0 then true else false
    }))
  |> filter(fn: (r) => r.is_anomaly == true)
  |> yield(name: "anomalies")
```

## Downsampling Tasks

Create tasks for automatic downsampling to reduce storage and improve long-term query performance.

### Hourly Aggregation Task

```flux
option task = {name: "downsample_hourly", every: 1h}

from(bucket: "cold_storage")
  |> range(start: -1h)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> aggregateWindow(every: 1h, fn: mean, createEmpty: false)
  |> to(bucket: "cold_storage_downsampled", org: "smart_cooling")
```

### Daily Aggregation Task

```flux
option task = {name: "downsample_daily", every: 1d}

from(bucket: "cold_storage")
  |> range(start: -1d)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> aggregateWindow(every: 1d, fn: mean, createEmpty: false)
  |> to(bucket: "analytics", org: "smart_cooling")
```

## API Access

### Using InfluxDB API

```bash
# Query data using InfluxDB API
curl -XPOST 'http://localhost:8086/api/v2/query?org=smart_cooling' \
  --header 'Authorization: Token smart-cooling-super-secret-token' \
  --header 'Content-Type: application/vnd.flux' \
  --data 'from(bucket:"cold_storage") |> range(start: -1h)'
```

### Write Data

```bash
# Write line protocol data
curl -XPOST 'http://localhost:8086/api/v2/write?org=smart_cooling&bucket=cold_storage&precision=s' \
  --header 'Authorization: Token smart-cooling-super-secret-token' \
  --data-raw 'sensor_data,unitId=CS-01 temperature=4.2,humidity=67,compressorStatus="ON",energyConsumption=2.3'
```

### Using InfluxDB Client Libraries

**Node.js Example:**

```javascript
const {InfluxDB, Point} = require('@influxdata/influxdb-client');

const token = 'smart-cooling-super-secret-token';
const org = 'smart_cooling';
const bucket = 'cold_storage';
const url = 'http://localhost:8086';

const client = new InfluxDB({url, token});
const writeApi = client.getWriteApi(org, bucket);

const point = new Point('sensor_data')
  .tag('unitId', 'CS-01')
  .floatField('temperature', 4.2)
  .floatField('humidity', 67)
  .stringField('compressorStatus', 'ON')
  .floatField('energyConsumption', 2.3);

writeApi.writePoint(point);
writeApi.close();
```

**Python Example:**

```python
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

token = "smart-cooling-super-secret-token"
org = "smart_cooling"
bucket = "cold_storage"
url = "http://localhost:8086"

client = InfluxDBClient(url=url, token=token, org=org)
write_api = client.write_api(write_options=SYNCHRONOUS)

point = Point("sensor_data") \
    .tag("unitId", "CS-01") \
    .field("temperature", 4.2) \
    .field("humidity", 67) \
    .field("compressorStatus", "ON") \
    .field("energyConsumption", 2.3)

write_api.write(bucket=bucket, record=point)
```

## Retention Policies

Retention policies are set per bucket:

- **cold_storage**: 90 days - Primary operational data
- **alerts**: 365 days - Compliance and audit trail
- **analytics**: 730 days - Historical analysis
- **cold_storage_downsampled**: 1825 days - Long-term trends

Data is automatically deleted after the retention period expires.

## Backup and Restore

### Backup

```bash
# Backup all data
docker exec smart_cooling_influxdb \
  influx backup /backup/influxdb-backup -t smart-cooling-super-secret-token

# Copy backup from container
docker cp smart_cooling_influxdb:/backup/influxdb-backup ./backups/
```

### Restore

```bash
# Copy backup to container
docker cp ./backups/influxdb-backup smart_cooling_influxdb:/restore/

# Restore data
docker exec smart_cooling_influxdb \
  influx restore /restore/influxdb-backup -t smart-cooling-super-secret-token
```

## Performance Optimization

### Indexing

Tags are automatically indexed. Use tags for:
- Filtering (unitId, location)
- Grouping operations
- High-cardinality identifiers

Use fields for:
- Actual measurement values
- Calculated values
- Non-filtering data

### Query Optimization

1. **Use time ranges**: Always specify `range(start: -24h)` to limit data scanned
2. **Filter early**: Apply filters immediately after range
3. **Use appropriate aggregation**: Choose the right window size
4. **Limit results**: Use `limit()` when you don't need all data
5. **Use continuous queries**: Pre-aggregate common queries

### Monitoring

```bash
# Check bucket sizes
docker exec -it smart_cooling_influxdb \
  influx bucket list --org smart_cooling --token smart-cooling-super-secret-token

# View query performance
docker exec -it smart_cooling_influxdb \
  influx query 'from(bucket: "cold_storage") |> range(start: -1m) |> count()' \
  --org smart_cooling --token smart-cooling-super-secret-token
```

## Troubleshooting

### Connection Issues

```bash
# Test InfluxDB ping
curl http://localhost:8086/ping

# Check health
curl http://localhost:8086/health
```

### View Logs

```bash
docker-compose logs influxdb
```

### Verify Token

```bash
docker exec -it smart_cooling_influxdb \
  influx auth list --org smart_cooling --json
```

### Reset Database

```bash
# WARNING: This will delete all data
docker-compose down
docker volume rm smart_cooling_influxdb_data
docker-compose up -d influxdb
```

## Security Best Practices

1. **Change default token**: Update the token in production
2. **Create limited tokens**: Use separate tokens for read-only access
3. **Enable HTTPS**: Configure TLS for production
4. **Regular backups**: Automate backup procedures
5. **Monitor access**: Review auth logs regularly
6. **Rotate tokens**: Periodically update access tokens

## References

- [InfluxDB Documentation](https://docs.influxdata.com/influxdb/)
- [Flux Language](https://docs.influxdata.com/flux/)
- [InfluxDB API](https://docs.influxdata.com/influxdb/v2/api/)
- [Client Libraries](https://docs.influxdata.com/influxdb/v2/api-guide/client-libraries/)
