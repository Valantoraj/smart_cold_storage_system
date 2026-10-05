/**
 * Smart Cold Storage Digital Twin - REST API Server
 * 
 * Provides REST API endpoints for accessing:
 * - Storage unit data and status
 * - Historical sensor data from InfluxDB
 * - Digital twin state from Eclipse Ditto
 * - Alerts and notifications
 * - Predictive maintenance information
 */

const express = require('express');
const cors = require('cors');
const axios = require('axios');
const { InfluxDB } = require('@influxdata/influxdb-client');

const app = express();
const PORT = process.env.PORT || 3001;

// Middleware
app.use(cors());
app.use(express.json());

// Configuration
const config = {
  influxdb: {
    url: process.env.INFLUXDB_URL || 'http://influxdb:8086',
    token: process.env.INFLUXDB_TOKEN || 'smart-cooling-super-secret-token',
    org: process.env.INFLUXDB_ORG || 'smart_cooling',
    bucket: process.env.INFLUXDB_BUCKET || 'cold_storage'
  },
  ditto: {
    url: process.env.DITTO_URL || 'http://ditto-gateway:8080',
    apiVersion: 2
  }
};

// InfluxDB client
const influxDB = new InfluxDB({
  url: config.influxdb.url,
  token: config.influxdb.token
});

const queryApi = influxDB.getQueryApi(config.influxdb.org);

// =============================================================================
// Health Check
// =============================================================================

app.get('/api/health', (req, res) => {
  res.json({
    status: 'healthy',
    timestamp: new Date().toISOString(),
    services: {
      api: 'running',
      influxdb: config.influxdb.url,
      ditto: config.ditto.url
    }
  });
});

// =============================================================================
// Storage Units Endpoints
// =============================================================================

/**
 * GET /api/storage
 * List all storage units
 */
app.get('/api/storage', async (req, res) => {
  try {
    // Get all units from Ditto
    const response = await axios.get(
      `${config.ditto.url}/api/${config.ditto.apiVersion}/things`,
      {
        params: {
          'filter': 'like(thingId,"*:CS-*")'
        }
      }
    );

    const units = response.data.items || [];
    
    // Format response
    const formattedUnits = units.map(unit => ({
      unitId: unit.thingId.split(':')[1],
      location: unit.attributes?.location,
      status: unit.features?.status?.properties?.health || 'unknown',
      temperature: unit.features?.temperature?.properties?.value,
      lastUpdate: unit.features?.temperature?.properties?.lastUpdated
    }));

    res.json({
      count: formattedUnits.length,
      units: formattedUnits
    });

  } catch (error) {
    console.error('Error fetching storage units:', error.message);
    res.status(500).json({
      error: 'Failed to fetch storage units',
      message: error.message
    });
  }
});

/**
 * GET /api/storage/:id
 * Get detailed information for specific storage unit
 */
app.get('/api/storage/:id', async (req, res) => {
  try {
    const unitId = req.params.id;
    const thingId = `org.eclipse.ditto:${unitId}`;

    // Get digital twin from Ditto
    const response = await axios.get(
      `${config.ditto.url}/api/${config.ditto.apiVersion}/things/${thingId}`
    );

    const thing = response.data;

    // Format response
    const unitData = {
      unitId: unitId,
      attributes: thing.attributes,
      currentState: {
        temperature: thing.features?.temperature?.properties,
        humidity: thing.features?.humidity?.properties,
        compressor: thing.features?.compressor?.properties,
        energy: thing.features?.energy?.properties,
        status: thing.features?.status?.properties,
        connectivity: thing.features?.connectivity?.properties,
        maintenance: thing.features?.maintenance?.properties
      },
      lastUpdate: thing.features?.connectivity?.properties?.lastSeen
    };

    res.json(unitData);

  } catch (error) {
    if (error.response && error.response.status === 404) {
      res.status(404).json({
        error: 'Storage unit not found',
        unitId: req.params.id
      });
    } else {
      console.error('Error fetching storage unit:', error.message);
      res.status(500).json({
        error: 'Failed to fetch storage unit',
        message: error.message
      });
    }
  }
});

/**
 * GET /api/storage/:id/history
 * Get historical sensor data for a storage unit
 */
app.get('/api/storage/:id/history', async (req, res) => {
  try {
    const unitId = req.params.id;
    const { start = '-24h', end = 'now', fields = 'temperature,humidity,energyConsumption' } = req.query;

    const fieldList = fields.split(',').map(f => f.trim());
    const fieldFilter = fieldList.map(f => `r["_field"] == "${f}"`).join(' or ');

    const fluxQuery = `
      from(bucket: "${config.influxdb.bucket}")
        |> range(start: ${start}, stop: ${end})
        |> filter(fn: (r) => r["_measurement"] == "sensor_data")
        |> filter(fn: (r) => r["unitId"] == "${unitId}")
        |> filter(fn: (r) => ${fieldFilter})
        |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        |> sort(columns: ["_time"], desc: false)
    `;

    const data = [];
    await queryApi.queryRows(fluxQuery, {
      next(row, tableMeta) {
        const o = tableMeta.toObject(row);
        data.push({
          time: o._time,
          unitId: o.unitId,
          temperature: o.temperature,
          humidity: o.humidity,
          energyConsumption: o.energyConsumption,
          compressorStatus: o.compressorStatus
        });
      },
      error(error) {
        console.error('InfluxDB query error:', error);
      },
      complete() {
        // Query complete
      }
    });

    res.json({
      unitId: unitId,
      timeRange: { start, end },
      count: data.length,
      data: data
    });

  } catch (error) {
    console.error('Error fetching history:', error.message);
    res.status(500).json({
      error: 'Failed to fetch historical data',
      message: error.message
    });
  }
});

/**
 * GET /api/storage/:id/current
 * Get current (latest) sensor readings for a storage unit
 */
app.get('/api/storage/:id/current', async (req, res) => {
  try {
    const unitId = req.params.id;

    const fluxQuery = `
      from(bucket: "${config.influxdb.bucket}")
        |> range(start: -5m)
        |> filter(fn: (r) => r["_measurement"] == "sensor_data")
        |> filter(fn: (r) => r["unitId"] == "${unitId}")
        |> last()
        |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
    `;

    let currentData = null;
    await queryApi.queryRows(fluxQuery, {
      next(row, tableMeta) {
        const o = tableMeta.toObject(row);
        currentData = {
          unitId: o.unitId,
          temperature: o.temperature,
          humidity: o.humidity,
          compressorStatus: o.compressorStatus,
          energyConsumption: o.energyConsumption,
          timestamp: o._time
        };
      },
      error(error) {
        console.error('InfluxDB query error:', error);
      },
      complete() {
        // Query complete
      }
    });

    if (currentData) {
      res.json(currentData);
    } else {
      res.status(404).json({
        error: 'No recent data found',
        unitId: unitId
      });
    }

  } catch (error) {
    console.error('Error fetching current data:', error.message);
    res.status(500).json({
      error: 'Failed to fetch current data',
      message: error.message
    });
  }
});

// =============================================================================
// Alerts Endpoints
// =============================================================================

/**
 * GET /api/alerts
 * Get alerts for all units or filtered by parameters
 */
app.get('/api/alerts', async (req, res) => {
  try {
    const { severity, status = 'active', unitId, start = '-24h' } = req.query;

    let filters = [
      'r["_measurement"] == "alerts"'
    ];

    if (severity) {
      filters.push(`r["severity"] == "${severity}"`);
    }

    if (unitId) {
      filters.push(`r["unitId"] == "${unitId}"`);
    }

    if (status === 'active') {
      filters.push('(r["resolved"] == "false" or r["resolved"] == false)');
    }

    const fluxQuery = `
      from(bucket: "alerts")
        |> range(start: ${start})
        |> filter(fn: (r) => ${filters.join(' and ')})
        |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        |> sort(columns: ["_time"], desc: true)
        |> limit(n: 100)
    `;

    const alerts = [];
    await queryApi.queryRows(fluxQuery, {
      next(row, tableMeta) {
        const o = tableMeta.toObject(row);
        alerts.push({
          time: o._time,
          unitId: o.unitId,
          alertType: o.alertType,
          severity: o.severity,
          message: o.message,
          value: o.value,
          threshold: o.threshold,
          resolved: o.resolved
        });
      },
      error(error) {
        console.error('InfluxDB query error:', error);
      },
      complete() {
        // Query complete
      }
    });

    res.json({
      count: alerts.length,
      filters: { severity, status, unitId },
      alerts: alerts
    });

  } catch (error) {
    console.error('Error fetching alerts:', error.message);
    res.status(500).json({
      error: 'Failed to fetch alerts',
      message: error.message
    });
  }
});

/**
 * GET /api/storage/:id/alerts
 * Get alerts for a specific storage unit
 */
app.get('/api/storage/:id/alerts', async (req, res) => {
  try {
    const unitId = req.params.id;
    const { severity, status = 'active', start = '-24h' } = req.query;

    req.query.unitId = unitId;
    
    // Reuse the main alerts endpoint logic
    return app._router.handle({ ...req, url: '/api/alerts', query: req.query }, res);

  } catch (error) {
    console.error('Error fetching unit alerts:', error.message);
    res.status(500).json({
      error: 'Failed to fetch unit alerts',
      message: error.message
    });
  }
});

// =============================================================================
// Maintenance Endpoints
// =============================================================================

/**
 * GET /api/maintenance/scores
 * Get maintenance scores for all units
 */
app.get('/api/maintenance/scores', async (req, res) => {
  try {
    const units = ['CS-01', 'CS-02', 'CS-03'];
    const scores = [];

    for (const unitId of units) {
      const thingId = `org.eclipse.ditto:${unitId}`;
      
      try {
        const response = await axios.get(
          `${config.ditto.url}/api/${config.ditto.apiVersion}/things/${thingId}/features/maintenance`
        );

        scores.push({
          unitId: unitId,
          ...response.data.properties
        });
      } catch (error) {
        // Unit might not exist or have maintenance feature
        console.warn(`Could not fetch maintenance for ${unitId}`);
      }
    }

    res.json({
      count: scores.length,
      scores: scores
    });

  } catch (error) {
    console.error('Error fetching maintenance scores:', error.message);
    res.status(500).json({
      error: 'Failed to fetch maintenance scores',
      message: error.message
    });
  }
});

/**
 * GET /api/storage/:id/maintenance
 * Get maintenance information for specific unit
 */
app.get('/api/storage/:id/maintenance', async (req, res) => {
  try {
    const unitId = req.params.id;
    const thingId = `org.eclipse.ditto:${unitId}`;

    const response = await axios.get(
      `${config.ditto.url}/api/${config.ditto.apiVersion}/things/${thingId}/features/maintenance`
    );

    res.json({
      unitId: unitId,
      ...response.data.properties
    });

  } catch (error) {
    if (error.response && error.response.status === 404) {
      res.status(404).json({
        error: 'Maintenance data not found',
        unitId: req.params.id
      });
    } else {
      console.error('Error fetching maintenance data:', error.message);
      res.status(500).json({
        error: 'Failed to fetch maintenance data',
        message: error.message
      });
    }
  }
});

// =============================================================================
// Analytics Endpoints
// =============================================================================

/**
 * GET /api/analytics/summary
 * Get system-wide analytics summary
 */
app.get('/api/analytics/summary', async (req, res) => {
  try {
    const { start = '-24h' } = req.query;

    // Get average temperature for all units
    const tempQuery = `
      from(bucket: "${config.influxdb.bucket}")
        |> range(start: ${start})
        |> filter(fn: (r) => r["_measurement"] == "sensor_data")
        |> filter(fn: (r) => r["_field"] == "temperature")
        |> group(columns: ["unitId"])
        |> mean()
    `;

    // Get alert counts
    const alertQuery = `
      from(bucket: "alerts")
        |> range(start: ${start})
        |> filter(fn: (r) => r["_measurement"] == "alerts")
        |> group(columns: ["severity"])
        |> count()
    `;

    const temperatures = [];
    await queryApi.queryRows(tempQuery, {
      next(row, tableMeta) {
        const o = tableMeta.toObject(row);
        temperatures.push({
          unitId: o.unitId,
          avgTemperature: parseFloat(o._value.toFixed(2))
        });
      },
      error(error) {
        console.error('InfluxDB query error:', error);
      },
      complete() {}
    });

    const alertCounts = {};
    await queryApi.queryRows(alertQuery, {
      next(row, tableMeta) {
        const o = tableMeta.toObject(row);
        alertCounts[o.severity] = o._value;
      },
      error(error) {
        console.error('InfluxDB query error:', error);
      },
      complete() {}
    });

    res.json({
      timeRange: start,
      temperatures: temperatures,
      alerts: alertCounts,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error fetching analytics:', error.message);
    res.status(500).json({
      error: 'Failed to fetch analytics',
      message: error.message
    });
  }
});

// =============================================================================
// Digital Twin Endpoints
// =============================================================================

/**
 * GET /api/twins
 * List all digital twins
 */
app.get('/api/twins', async (req, res) => {
  try {
    const response = await axios.get(
      `${config.ditto.url}/api/${config.ditto.apiVersion}/things`
    );

    res.json({
      count: response.data.items?.length || 0,
      things: response.data.items || []
    });

  } catch (error) {
    console.error('Error fetching digital twins:', error.message);
    res.status(500).json({
      error: 'Failed to fetch digital twins',
      message: error.message
    });
  }
});

/**
 * GET /api/twins/:thingId
 * Get specific digital twin
 */
app.get('/api/twins/:thingId', async (req, res) => {
  try {
    const thingId = req.params.thingId;

    const response = await axios.get(
      `${config.ditto.url}/api/${config.ditto.apiVersion}/things/${thingId}`
    );

    res.json(response.data);

  } catch (error) {
    if (error.response && error.response.status === 404) {
      res.status(404).json({
        error: 'Digital twin not found',
        thingId: req.params.thingId
      });
    } else {
      console.error('Error fetching digital twin:', error.message);
      res.status(500).json({
        error: 'Failed to fetch digital twin',
        message: error.message
      });
    }
  }
});

// =============================================================================
// Error Handling
// =============================================================================

// 404 handler
app.use((req, res) => {
  res.status(404).json({
    error: 'Endpoint not found',
    path: req.path
  });
});

// General error handler
app.use((err, req, res, next) => {
  console.error('Unhandled error:', err);
  res.status(500).json({
    error: 'Internal server error',
    message: err.message
  });
});

// =============================================================================
// Server Startup
// =============================================================================

app.listen(PORT, () => {
  console.log('='.repeat(60));
  console.log('Smart Cold Storage Digital Twin - REST API');
  console.log('='.repeat(60));
  console.log(`Server running on port ${PORT}`);
  console.log(`Health check: http://localhost:${PORT}/api/health`);
  console.log('');
  console.log('Configuration:');
  console.log(`  InfluxDB: ${config.influxdb.url}`);
  console.log(`  Ditto:    ${config.ditto.url}`);
  console.log('');
  console.log('API Endpoints:');
  console.log('  GET  /api/health');
  console.log('  GET  /api/storage');
  console.log('  GET  /api/storage/:id');
  console.log('  GET  /api/storage/:id/current');
  console.log('  GET  /api/storage/:id/history');
  console.log('  GET  /api/storage/:id/alerts');
  console.log('  GET  /api/storage/:id/maintenance');
  console.log('  GET  /api/alerts');
  console.log('  GET  /api/maintenance/scores');
  console.log('  GET  /api/analytics/summary');
  console.log('  GET  /api/twins');
  console.log('  GET  /api/twins/:thingId');
  console.log('='.repeat(60));
});

module.exports = app;
