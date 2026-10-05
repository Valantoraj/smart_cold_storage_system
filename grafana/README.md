# Grafana Dashboards Configuration

## Overview

Grafana provides the visualization and monitoring interface for the Smart Cold Storage Digital Twin system. It displays real-time and historical data from InfluxDB, showing temperature trends, energy consumption, compressor status, alerts, and predictive maintenance scores.

## Directory Structure

```
grafana/
├── dashboards/                    # Dashboard JSON files
│   ├── overview-dashboard.json   # Main overview dashboard
│   ├── unit-detail-dashboard.json # Individual unit details
│   ├── predictive-maintenance-dashboard.json # Maintenance view
│   └── alerts-dashboard.json     # Alert management
├── provisioning/
│   ├── datasources/
│   │   └── datasources.yml       # InfluxDB datasource config
│   └── dashboards/
│       └── dashboards.yml         # Dashboard provisioning config
└── README.md                      # This file
```

## Access

**URL**: http://localhost:3000

**Default Credentials**:
- Username: `admin`
- Password: `admin`

**Note**: You'll be prompted to change the password on first login.

## Configured Dashboards

### 1. Cold Storage Overview

**Purpose**: High-level view of all cold storage units

**Panels**:
- **Temperature Gauges**: Current temperature for each unit (CS-01, CS-02, CS-03)
- **Temperature Trends**: Line chart showing temperature over time for all units
- **Compressor Status**: Donut chart showing current compressor states
- **Energy Consumption**: Line chart showing energy usage trends
- **Active Alerts**: Table of current unresolved alerts

**Refresh Rate**: Every 10 seconds

**Time Range**: Last 6 hours (adjustable)

**Use Cases**:
- Quick status check of all units
- Identify units with issues
- Monitor trends at a glance

### 2. Unit Detail Dashboard (Template)

**Purpose**: Detailed view of a single cold storage unit

**Panels**:
- **Current Metrics**: Temperature, Humidity, Energy, Compressor Status
- **Temperature History**: 24-hour temperature trend with thresholds
- **Humidity History**: 24-hour humidity trend
- **Energy Consumption**: Hourly and daily energy usage
- **Compressor Runtime**: ON/OFF cycles and runtime percentage
- **Maintenance Score**: Current predictive maintenance score
- **Alert History**: Recent alerts for this unit
- **Status Timeline**: State changes over time

**Features**:
- Variable selector to choose which unit to view
- Drill-down from overview dashboard
- Export data functionality

### 3. Predictive Maintenance Dashboard

**Purpose**: Monitor equipment health and maintenance needs

**Panels**:
- **Maintenance Scores**: Gauges for all units
- **Component Health**: Temperature stability, energy efficiency, compressor health
- **Maintenance Priority**: Units sorted by urgency
- **Trend Analysis**: Historical maintenance scores
- **Recommendation Panel**: Current maintenance recommendations
- **Time to Maintenance**: Estimated time before attention needed
- **Maintenance History**: Past maintenance actions and outcomes

**Use Cases**:
- Identify units needing attention
- Prioritize maintenance activities
- Track equipment degradation over time

### 4. Alerts Dashboard

**Purpose**: Alert management and history

**Panels**:
- **Active Alerts**: Critical alerts requiring immediate attention
- **Alert Timeline**: Chronological view of all alerts
- **Alerts by Type**: Breakdown by alert category
- **Alerts by Severity**: Critical, Warning, Info counts
- **Alert Frequency**: Number of alerts per unit over time
- **Resolution Time**: How long alerts stay active
- **Alert History Table**: Searchable, filterable alert log

**Features**:
- Filter by severity, type, unit
- Mark alerts as acknowledged
- Link to unit detail dashboard

## Datasources

### 1. InfluxDB Cold Storage

- **Type**: InfluxDB (Flux)
- **URL**: http://influxdb:8086
- **Organization**: smart_cooling
- **Default Bucket**: cold_storage
- **Token**: smart-cooling-super-secret-token

**Used for**:
- Sensor data (temperature, humidity, energy, compressor)
- Real-time measurements
- Historical trends

### 2. InfluxDB Alerts

- **Type**: InfluxDB (Flux)
- **Organization**: smart_cooling
- **Bucket**: alerts
- **Token**: smart-cooling-super-secret-token

**Used for**:
- Alert data
- Alert history
- Alert analytics

### 3. InfluxDB Analytics

- **Type**: InfluxDB (Flux)
- **Organization**: smart_cooling
- **Bucket**: analytics
- **Token**: smart-cooling-super-secret-token

**Used for**:
- Maintenance scores
- Aggregated analytics
- Long-term statistics

## Common Flux Queries

### Get Current Temperature

```flux
from(bucket: "cold_storage")
  |> range(start: -5m)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> filter(fn: (r) => r["unitId"] == "CS-01")
  |> filter(fn: (r) => r["_field"] == "temperature")
  |> last()
```

### Temperature Trend (Last 24 Hours)

```flux
from(bucket: "cold_storage")
  |> range(start: -24h)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> filter(fn: (r) => r["_field"] == "temperature")
  |> aggregateWindow(every: 5m, fn: mean, createEmpty: false)
```

### Active Alerts

```flux
from(bucket: "alerts")
  |> range(start: -24h)
  |> filter(fn: (r) => r["_measurement"] == "alerts")
  |> filter(fn: (r) => r["resolved"] == false)
  |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> sort(columns: ["_time"], desc: true)
```

### Maintenance Scores

```flux
from(bucket: "analytics")
  |> range(start: -7d)
  |> filter(fn: (r) => r["_measurement"] == "maintenance_score")
  |> filter(fn: (r) => r["_field"] == "score")
```

### Compressor Runtime Percentage

```flux
import "strings"

data = from(bucket: "cold_storage")
  |> range(start: -1h)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> filter(fn: (r) => r["unitId"] == "CS-01")
  |> filter(fn: (r) => r["_field"] == "compressorStatus")

total = data |> count()
on_count = data |> filter(fn: (r) => r["_value"] == "ON") |> count()

// Calculate percentage
```

## Panel Types and Use Cases

### Gauge

**Best for**: Current single values with thresholds
- Temperature
- Humidity
- Maintenance score
- Energy consumption

**Configuration**:
- Min: 0, Max: 10 (for temperature)
- Thresholds: Green (0-6), Yellow (6-8), Red (8+)

### Time Series (Line Chart)

**Best for**: Trends over time
- Temperature history
- Energy consumption
- Humidity trends

**Configuration**:
- Line interpolation: Smooth
- Fill opacity: 10%
- Point size: Auto
- Legend: Show with mean and last values

### Table

**Best for**: Lists of data with multiple columns
- Active alerts
- Alert history
- Unit status

**Configuration**:
- Sort by time (descending)
- Enable filtering
- Show pagination

### Stat

**Best for**: Single number with trend
- Total alerts
- Units online
- Average temperature

**Configuration**:
- Show trend sparkline
- Color by thresholds

### Pie/Donut Chart

**Best for**: Proportions and distributions
- Compressor ON/OFF status
- Alert severity distribution
- Units by health status

**Configuration**:
- Show labels
- Display percentages

### Bar Chart

**Best for**: Comparisons across categories
- Energy by unit
- Alerts by type
- Maintenance priority

## Threshold Configuration

### Temperature

```json
{
  "mode": "absolute",
  "steps": [
    { "color": "green", "value": null },
    { "color": "yellow", "value": 6 },
    { "color": "red", "value": 8 }
  ]
}
```

### Humidity

```json
{
  "mode": "absolute",
  "steps": [
    { "color": "red", "value": null },
    { "color": "green", "value": 50 },
    { "color": "green", "value": 80 },
    { "color": "red", "value": 81 }
  ]
}
```

### Energy

```json
{
  "mode": "absolute",
  "steps": [
    { "color": "green", "value": null },
    { "color": "yellow", "value": 3 },
    { "color": "red", "value": 4 }
  ]
}
```

### Maintenance Score

```json
{
  "mode": "absolute",
  "steps": [
    { "color": "green", "value": null },
    { "color": "yellow", "value": 40 },
    { "color": "orange", "value": 60 },
    { "color": "red", "value": 80 }
  ]
}
```

## Variables

### Unit Selector

Create a variable to select different units:

**Name**: `unit`  
**Type**: Custom  
**Values**: `CS-01,CS-02,CS-03`  
**Multi-value**: No  
**Include All**: No  

**Usage in queries**:
```flux
filter(fn: (r) => r["unitId"] == "${unit}")
```

### Time Range Shortcuts

- Last 15 minutes
- Last 1 hour
- Last 6 hours
- Last 24 hours
- Last 7 days
- Last 30 days

## Alerts in Grafana

### Alert Rules

Configure Grafana alerts for critical conditions:

#### High Temperature Alert

**Condition**: Temperature > 8°C for 5 minutes  
**Notification**: Email, Slack, or PagerDuty  
**Severity**: Critical

#### Energy Anomaly Alert

**Condition**: Energy > 4 kW for 10 minutes  
**Notification**: Email  
**Severity**: Warning

#### Missing Data Alert

**Condition**: No data for 15 minutes  
**Notification**: Email  
**Severity**: Warning

## Provisioning

Grafana automatically loads:

1. **Datasources**: Configured from `provisioning/datasources/datasources.yml`
2. **Dashboards**: Loaded from `grafana/dashboards/` directory

### Auto-Provisioning Benefits

- Consistent configuration across environments
- Version control for dashboards
- No manual setup required
- Easy replication

## Customization

### Adding a New Panel

1. Click "Add panel" in dashboard edit mode
2. Select visualization type
3. Configure data source and query
4. Set thresholds and formatting
5. Save panel

### Importing Dashboards

1. Go to Dashboards → Import
2. Upload JSON file or paste JSON
3. Select datasource
4. Click Import

### Exporting Dashboards

1. Open dashboard
2. Click share icon → Export
3. Save JSON file
4. Commit to version control

## Best Practices

### Query Optimization

1. **Use appropriate time ranges**: Don't query years of data for live views
2. **Aggregate data**: Use `aggregateWindow()` for downsampling
3. **Limit results**: Use `limit()` for tables
4. **Filter early**: Apply filters before aggregations

### Dashboard Design

1. **Logical grouping**: Group related panels
2. **Consistent colors**: Use color scheme across dashboards
3. **Appropriate visualizations**: Choose right chart type for data
4. **Avoid clutter**: Don't overcrowd dashboards
5. **Use templates**: Create variables for dynamic dashboards

### Performance

1. **Refresh rate**: Balance freshness vs. load (10-30 seconds)
2. **Query caching**: Enable query caching in Grafana
3. **Panel limits**: Keep dashboards under 20 panels
4. **Lazy loading**: Enable lazy loading for complex dashboards

## Troubleshooting

### No Data Appearing

**Checks**:
1. InfluxDB is running: `docker ps | grep influxdb`
2. Data is being written: Check InfluxDB bucket
3. Datasource configured correctly: Test connection in Grafana
4. Query syntax correct: Test query in InfluxDB UI
5. Time range appropriate: Check dashboard time picker

### Slow Dashboards

**Solutions**:
1. Reduce time range
2. Increase refresh interval
3. Add aggregation to queries
4. Limit number of series
5. Use query caching

### Connection Errors

**Checks**:
1. Verify InfluxDB URL: http://influxdb:8086
2. Check token validity
3. Verify organization and bucket names
4. Check Docker network connectivity
5. Review Grafana logs: `docker logs smart_cooling_grafana`

## Mobile Access

Grafana dashboards are responsive and work on mobile devices:

1. Access http://localhost:3000 from mobile browser
2. Use Grafana mobile app (iOS/Android)
3. Configure push notifications for alerts

## Security

### Production Configuration

1. **Change default password**: Use strong admin password
2. **Create users**: Add individual user accounts
3. **Set permissions**: Limit dashboard editing
4. **Enable HTTPS**: Use TLS for connections
5. **Rotate tokens**: Regularly update InfluxDB tokens

### Access Control

Create roles:
- **Admin**: Full access
- **Editor**: Edit dashboards
- **Viewer**: Read-only access

## Integration

### Embedding Dashboards

Embed in other applications:

```html
<iframe
  src="http://localhost:3000/d/cold-storage-overview?orgId=1&refresh=10s&kiosk"
  width="1200"
  height="800"
  frameborder="0">
</iframe>
```

### Grafana API

Programmatic access:

```bash
# Get dashboard
curl -H "Authorization: Bearer <api-key>" \
  http://localhost:3000/api/dashboards/uid/cold-storage-overview

# Create annotation
curl -X POST -H "Authorization: Bearer <api-key>" \
  -H "Content-Type: application/json" \
  -d '{"text":"Maintenance performed","tags":["maintenance"]}' \
  http://localhost:3000/api/annotations
```

## Resources

- [Grafana Documentation](https://grafana.com/docs/)
- [InfluxDB Flux Language](https://docs.influxdata.com/flux/)
- [Dashboard Best Practices](https://grafana.com/docs/grafana/latest/best-practices/)
- [Grafana Provisioning](https://grafana.com/docs/grafana/latest/administration/provisioning/)
