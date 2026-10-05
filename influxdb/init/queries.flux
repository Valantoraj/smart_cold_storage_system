// InfluxDB Flux Query Collection
// Smart Cold Storage Digital Twin System

// =============================================================================
// BASIC QUERIES
// =============================================================================

// Get last 24 hours of all data for a specific unit
from(bucket: "cold_storage")
  |> range(start: -24h)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> filter(fn: (r) => r["unitId"] == "CS-01")
  |> yield(name: "last_24h")

// Get current (latest) values for all units
from(bucket: "cold_storage")
  |> range(start: -5m)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> last()
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> yield(name: "current_status")

// Get specific field for specific time range
from(bucket: "cold_storage")
  |> range(start: 2026-10-01T00:00:00Z, stop: 2026-10-05T23:59:59Z)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> filter(fn: (r) => r["unitId"] == "CS-02")
  |> filter(fn: (r) => r["_field"] == "temperature")
  |> yield(name: "temperature_range")

// =============================================================================
// AGGREGATION QUERIES
// =============================================================================

// Hourly average temperature
from(bucket: "cold_storage")
  |> range(start: -7d)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> filter(fn: (r) => r["_field"] == "temperature")
  |> aggregateWindow(every: 1h, fn: mean, createEmpty: false)
  |> yield(name: "hourly_avg_temp")

// Daily min/max/mean temperature
from(bucket: "cold_storage")
  |> range(start: -30d)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> filter(fn: (r) => r["unitId"] == "CS-01")
  |> filter(fn: (r) => r["_field"] == "temperature")
  |> aggregateWindow(every: 1d, fn: mean, createEmpty: false)
  |> yield(name: "daily_mean")

// Calculate average energy consumption by unit
from(bucket: "cold_storage")
  |> range(start: -24h)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> filter(fn: (r) => r["_field"] == "energyConsumption")
  |> group(columns: ["unitId"])
  |> mean()
  |> yield(name: "avg_energy_by_unit")

// =============================================================================
// TREND ANALYSIS
// =============================================================================

// Detect temperature rising trend (positive derivative)
from(bucket: "cold_storage")
  |> range(start: -1h)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> filter(fn: (r) => r["unitId"] == "CS-01")
  |> filter(fn: (r) => r["_field"] == "temperature")
  |> derivative(unit: 1m, nonNegative: false)
  |> filter(fn: (r) => r["_value"] > 0.1)
  |> yield(name: "rising_trend")

// Calculate rate of change for energy consumption
from(bucket: "cold_storage")
  |> range(start: -24h)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> filter(fn: (r) => r["unitId"] == "CS-01")
  |> filter(fn: (r) => r["_field"] == "energyConsumption")
  |> derivative(unit: 1h)
  |> yield(name: "energy_rate_of_change")

// Moving average for temperature
from(bucket: "cold_storage")
  |> range(start: -24h)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> filter(fn: (r) => r["unitId"] == "CS-01")
  |> filter(fn: (r) => r["_field"] == "temperature")
  |> movingAverage(n: 10)
  |> yield(name: "temp_moving_avg")

// =============================================================================
// COMPRESSOR ANALYSIS
// =============================================================================

// Count compressor ON periods in last 24 hours
from(bucket: "cold_storage")
  |> range(start: -24h)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> filter(fn: (r) => r["unitId"] == "CS-01")
  |> filter(fn: (r) => r["_field"] == "compressorStatus")
  |> filter(fn: (r) => r["_value"] == "ON")
  |> count()
  |> yield(name: "compressor_on_count")

// Calculate compressor ON percentage
compressor_data = from(bucket: "cold_storage")
  |> range(start: -24h)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> filter(fn: (r) => r["unitId"] == "CS-01")
  |> filter(fn: (r) => r["_field"] == "compressorStatus")

total_count = compressor_data |> count()
on_count = compressor_data |> filter(fn: (r) => r["_value"] == "ON") |> count()

union(tables: [total_count, on_count])
  |> pivot(rowKey: ["unitId"], columnKey: ["_field"], valueColumn: "_value")
  |> map(fn: (r) => ({ r with on_percentage: float(v: r.on) / float(v: r.total) * 100.0 }))
  |> yield(name: "compressor_on_percentage")

// =============================================================================
// ALERT QUERIES
// =============================================================================

// Get active alerts
from(bucket: "alerts")
  |> range(start: -30d)
  |> filter(fn: (r) => r["_measurement"] == "alerts")
  |> filter(fn: (r) => r["_field"] == "resolved")
  |> filter(fn: (r) => r["_value"] == false)
  |> sort(columns: ["_time"], desc: true)
  |> yield(name: "active_alerts")

// Count alerts by type in last 7 days
from(bucket: "alerts")
  |> range(start: -7d)
  |> filter(fn: (r) => r["_measurement"] == "alerts")
  |> group(columns: ["alertType"])
  |> count()
  |> yield(name: "alerts_by_type")

// Get critical alerts count per unit
from(bucket: "alerts")
  |> range(start: -30d)
  |> filter(fn: (r) => r["_measurement"] == "alerts")
  |> filter(fn: (r) => r["severity"] == "critical")
  |> group(columns: ["unitId"])
  |> count()
  |> yield(name: "critical_alerts_per_unit")

// =============================================================================
// MULTI-UNIT COMPARISON
// =============================================================================

// Compare temperature across all units
from(bucket: "cold_storage")
  |> range(start: -24h)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> filter(fn: (r) => r["_field"] == "temperature")
  |> aggregateWindow(every: 1h, fn: mean, createEmpty: false)
  |> pivot(rowKey: ["_time"], columnKey: ["unitId"], valueColumn: "_value")
  |> yield(name: "temperature_comparison")

// Compare energy efficiency (temperature per kW)
from(bucket: "cold_storage")
  |> range(start: -24h)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> filter(fn: (r) => r["_field"] == "temperature" or r["_field"] == "energyConsumption")
  |> pivot(rowKey: ["_time", "unitId"], columnKey: ["_field"], valueColumn: "_value")
  |> map(fn: (r) => ({ r with efficiency: r.temperature / r.energyConsumption }))
  |> group(columns: ["unitId"])
  |> mean(column: "efficiency")
  |> yield(name: "energy_efficiency")

// =============================================================================
// ANOMALY DETECTION
// =============================================================================

// Statistical anomaly detection (z-score > 2)
import "contrib/tomhollingworth/events"

data = from(bucket: "cold_storage")
  |> range(start: -7d)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> filter(fn: (r) => r["unitId"] == "CS-01")
  |> filter(fn: (r) => r["_field"] == "temperature")

mean_val = data |> mean() |> findRecord(fn: (key) => true, idx: 0)
stddev_val = data |> stddev() |> findRecord(fn: (key) => true, idx: 0)

data
  |> map(fn: (r) => ({
      r with
      zscore: (r._value - mean_val._value) / stddev_val._value,
      is_anomaly: if math.abs(x: (r._value - mean_val._value) / stddev_val._value) > 2.0 then true else false
    }))
  |> filter(fn: (r) => r.is_anomaly == true)
  |> yield(name: "statistical_anomalies")

// Threshold-based anomaly detection
from(bucket: "cold_storage")
  |> range(start: -24h)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> filter(fn: (r) => r["_field"] == "temperature")
  |> filter(fn: (r) => r["_value"] > 8.0 or r["_value"] < 2.0)
  |> yield(name: "temperature_threshold_violations")

// =============================================================================
// PREDICTIVE MAINTENANCE QUERIES
// =============================================================================

// Identify units with increasing temperature trend
from(bucket: "cold_storage")
  |> range(start: -6h)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> filter(fn: (r) => r["_field"] == "temperature")
  |> derivative(unit: 1h)
  |> filter(fn: (r) => r["_value"] > 0.5)
  |> group(columns: ["unitId"])
  |> count()
  |> filter(fn: (r) => r["_value"] > 3)
  |> yield(name: "sustained_temp_increase")

// Combine temperature, energy, and compressor for maintenance prediction
temp_trend = from(bucket: "cold_storage")
  |> range(start: -6h)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> filter(fn: (r) => r["_field"] == "temperature")
  |> derivative(unit: 1h)
  |> mean()
  |> map(fn: (r) => ({ r with metric: "temp_trend" }))

energy_increase = from(bucket: "cold_storage")
  |> range(start: -6h)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> filter(fn: (r) => r["_field"] == "energyConsumption")
  |> derivative(unit: 1h)
  |> mean()
  |> map(fn: (r) => ({ r with metric: "energy_trend" }))

union(tables: [temp_trend, energy_increase])
  |> pivot(rowKey: ["unitId"], columnKey: ["metric"], valueColumn: "_value")
  |> filter(fn: (r) => r.temp_trend > 0.3 and r.energy_trend > 0.1)
  |> yield(name: "maintenance_candidates")

// =============================================================================
// PERFORMANCE METRICS
// =============================================================================

// Calculate uptime percentage (when data is being received)
from(bucket: "cold_storage")
  |> range(start: -24h)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> group(columns: ["unitId"])
  |> count()
  |> map(fn: (r) => ({ r with uptime_pct: float(v: r._value) / 1440.0 * 100.0 }))
  |> yield(name: "uptime_percentage")

// Average response time between measurements
from(bucket: "cold_storage")
  |> range(start: -1h)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> filter(fn: (r) => r["_field"] == "temperature")
  |> elapsed(unit: 1s)
  |> group(columns: ["unitId"])
  |> mean()
  |> yield(name: "avg_measurement_interval")

// =============================================================================
// DATA QUALITY CHECKS
// =============================================================================

// Find missing data gaps (more than 5 minutes between measurements)
from(bucket: "cold_storage")
  |> range(start: -24h)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> filter(fn: (r) => r["_field"] == "temperature")
  |> elapsed(unit: 1s)
  |> filter(fn: (r) => r.elapsed > 300)
  |> yield(name: "data_gaps")

// Count measurements per unit (data availability)
from(bucket: "cold_storage")
  |> range(start: -24h)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> group(columns: ["unitId"])
  |> count()
  |> yield(name: "measurement_count")

// =============================================================================
// EXPORT QUERIES
// =============================================================================

// Export last 24h data for analysis
from(bucket: "cold_storage")
  |> range(start: -24h)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> pivot(rowKey: ["_time", "unitId"], columnKey: ["_field"], valueColumn: "_value")
  |> yield(name: "export_data")

// =============================================================================
// DASHBOARD QUERIES
// =============================================================================

// Dashboard overview - current status of all units
from(bucket: "cold_storage")
  |> range(start: -5m)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> last()
  |> pivot(rowKey: ["unitId"], columnKey: ["_field"], valueColumn: "_value")
  |> yield(name: "dashboard_overview")

// Dashboard temperature chart - last 6 hours
from(bucket: "cold_storage")
  |> range(start: -6h)
  |> filter(fn: (r) => r["_measurement"] == "sensor_data")
  |> filter(fn: (r) => r["_field"] == "temperature")
  |> aggregateWindow(every: 5m, fn: mean, createEmpty: false)
  |> yield(name: "dashboard_temp_chart")
