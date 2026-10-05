# Smart Cold Storage Digital Twin - Setup Guide

## Prerequisites

### Required Software

1. **Docker** (version 20.10 or higher)
   - Download: https://www.docker.com/products/docker-desktop
   - Verify: `docker --version`

2. **Docker Compose** (version 2.0 or higher)
   - Usually included with Docker Desktop
   - Verify: `docker-compose --version`

3. **Python 3.8+** (for sensor simulator)
   - Download: https://www.python.org/downloads/
   - Verify: `python --version`

4. **Git** (optional, for version control)
   - Download: https://git-scm.com/downloads
   - Verify: `git --version`

### System Requirements

- **RAM**: 8 GB minimum, 16 GB recommended
- **Disk Space**: 10 GB free space
- **CPU**: 4 cores recommended
- **OS**: Windows 10/11, macOS, or Linux

## Installation Steps

### 1. Clone or Download the Project

```bash
# If using Git
git clone <repository-url>
cd smart_cooling

# Or download and extract the ZIP file
```

### 2. Start the Docker Services

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Check status
docker ps
```

**Expected containers**:
- smart_cooling_mosquitto (MQTT Broker)
- smart_cooling_influxdb (Time-series Database)
- smart_cooling_mongodb (Ditto storage)
- smart_cooling_ditto_gateway (Digital Twin API)
- smart_cooling_ditto_policies
- smart_cooling_ditto_things
- smart_cooling_ditto_things_search
- smart_cooling_ditto_connectivity
- smart_cooling_nodered (Data Processing)
- smart_cooling_grafana (Visualization)
- smart_cooling_api (REST API)

### 3. Wait for Services to Initialize

Services need time to start up completely (2-5 minutes):

```bash
# Check all containers are healthy
docker ps --filter "name=smart_cooling" --format "table {{.Names}}\t{{.Status}}"

# Or use the test script
cd tests
./test-system.ps1  # Windows PowerShell
./test-system.sh   # Linux/Mac
```

### 4. Initialize Eclipse Ditto Digital Twins

```bash
# Windows PowerShell
cd ditto
.\init-ditto.ps1

# Linux/Mac
cd ditto
chmod +x init-ditto.sh
./init-ditto.sh
```

This creates:
- Policy for access control
- Digital twins for CS-01, CS-02, CS-03

### 5. Install Python Dependencies for Simulator

```bash
cd simulator
pip install -r requirements.txt
```

### 6. Verify Installation

Run the test suite:

```bash
# Windows PowerShell
cd tests
.\test-system.ps1

# Linux/Mac
cd tests
chmod +x test-api.sh
./test-api.sh
```

## Access the Services

### Web Interfaces

| Service | URL | Credentials |
|---------|-----|-------------|
| **Grafana** | http://localhost:3000 | admin / admin |
| **Node-RED** | http://localhost:1880 | None |
| **InfluxDB** | http://localhost:8086 | admin / adminpass123 |
| **Eclipse Ditto** | http://localhost:8080 | None (development) |
| **REST API** | http://localhost:3001/api | None |

### Service Endpoints

```bash
# REST API Health
curl http://localhost:3001/api/health

# InfluxDB Health
curl http://localhost:8086/health

# Ditto Health
curl http://localhost:8080/health

# Grafana Health
curl http://localhost:3000/api/health
```

## Running the Sensor Simulator

### Basic Usage

```bash
cd simulator

# Normal operation for all units
python sensor_simulator.py

# Specific scenario
python sensor_simulator.py --units CS-01:temp_rising CS-02:normal CS-03:high_energy

# Fast testing (10-second intervals)
python sensor_simulator.py --interval 10 --duration 300
```

### Available Scenarios

- `normal`: Normal operation
- `temp_rising`: Temperature gradually rising
- `temp_fluctuating`: Temperature fluctuating wildly
- `high_energy`: High energy consumption
- `humidity_issue`: Humidity out of range
- `equipment_degradation`: Equipment degrading
- `door_open`: Door left open
- `compressor_failure`: Compressor failure

## Viewing Data

### 1. Grafana Dashboards

1. Open http://localhost:3000
2. Login (admin/admin)
3. Navigate to "Dashboards" → "Cold Storage Overview"
4. View real-time data and trends

### 2. Node-RED Flows

1. Open http://localhost:1880
2. View the Main Data Flow tab
3. Open debug panel (right sidebar)
4. See incoming MQTT messages and alerts

### 3. REST API

```bash
# Get all storage units
curl http://localhost:3001/api/storage

# Get unit details
curl http://localhost:3001/api/storage/CS-01

# Get current readings
curl http://localhost:3001/api/storage/CS-01/current

# Get historical data (last 24 hours)
curl http://localhost:3001/api/storage/CS-01/history

# Get active alerts
curl http://localhost:3001/api/alerts?status=active

# Get maintenance scores
curl http://localhost:3001/api/maintenance/scores
```

## Testing Scenarios

### Scenario 1: Normal Operation

```bash
# Start simulator with normal operation
python sensor_simulator.py --units CS-01:normal CS-02:normal CS-03:normal --interval 30 --duration 600

# Expected:
# - Temperature stays 2-6°C
# - No alerts generated
# - Maintenance scores remain low
# - Grafana shows stable trends
```

### Scenario 2: Temperature Alert

```bash
# Start simulator with rising temperature
python sensor_simulator.py --units CS-01:temp_rising --interval 20 --duration 600

# Expected:
# - Temperature increases gradually
# - Warning alert at 6°C
# - Critical alert at 8°C
# - Alert appears in Grafana and API
```

### Scenario 3: Predictive Maintenance

```bash
# Start simulator with equipment degradation
python sensor_simulator.py --units CS-02:equipment_degradation --interval 30 --duration 1800

# Expected after 15-20 minutes:
# - Maintenance score increases
# - Temperature, energy, and compressor trends show degradation
# - Predictive maintenance alert generated
# - Priority escalates to "high"
```

### Scenario 4: Multiple Issues

```bash
# Simulate multiple problems
python sensor_simulator.py \
  --units CS-01:temp_rising CS-02:high_energy CS-03:humidity_issue \
  --interval 30 --duration 1200

# Expected:
# - Different alerts for each unit
# - Dashboard shows multiple units with issues
# - API returns alerts for different types
```

## Troubleshooting

### Containers Not Starting

```bash
# Check logs
docker-compose logs [service-name]

# Common issues:
# - Port already in use: Change ports in docker-compose.yml
# - Insufficient memory: Increase Docker memory allocation
# - Permission issues: Run with appropriate permissions
```

### No Data in Grafana

**Checks**:
1. Is the simulator running?
2. Is Mosquitto receiving messages? `docker logs smart_cooling_mosquitto`
3. Is Node-RED processing data? Check http://localhost:1880
4. Is InfluxDB receiving writes? Query data via InfluxDB UI
5. Are Grafana datasources configured? Check Grafana → Configuration → Data Sources

### Digital Twins Not Found

```bash
# Reinitialize Ditto
cd ditto
.\init-ditto.ps1  # Windows
./init-ditto.sh   # Linux/Mac

# Verify twins exist
curl http://localhost:8080/api/2/things
```

### API Not Responding

```bash
# Check API container
docker logs smart_cooling_api

# Restart API
docker-compose restart api

# Test connectivity
curl http://localhost:3001/api/health
```

### Node-RED Flows Not Processing

1. Open Node-RED: http://localhost:1880
2. Check if flows are deployed (red "Deploy" button means changes not saved)
3. Click "Deploy" to activate flows
4. Check debug panel for errors
5. Verify MQTT and InfluxDB nodes are connected (green status)

## Stopping the System

### Stop All Services

```bash
# Stop containers (preserves data)
docker-compose stop

# Stop and remove containers (preserves data volumes)
docker-compose down

# Stop and remove everything including data
docker-compose down -v
```

### Stop Simulator

```bash
# Press Ctrl+C in the terminal running the simulator
```

## Resetting the System

### Reset Data Only

```bash
# Remove data volumes
docker-compose down -v

# Restart services
docker-compose up -d

# Reinitialize Ditto
cd ditto
.\init-ditto.ps1  # or ./init-ditto.sh
```

### Complete Reset

```bash
# Remove everything
docker-compose down -v --rmi all

# Rebuild and start
docker-compose build
docker-compose up -d
```

## Updating the System

### Pull Latest Changes

```bash
# If using Git
git pull

# Rebuild containers if needed
docker-compose build

# Restart services
docker-compose down
docker-compose up -d
```

### Update Individual Service

```bash
# Rebuild specific service
docker-compose build [service-name]

# Restart that service
docker-compose up -d [service-name]
```

## Performance Tuning

### For Low-Resource Systems

Edit `docker-compose.yml`:

```yaml
# Reduce InfluxDB memory
influxdb:
  environment:
    - INFLUXD_QUERY_MEMORY_BYTES=1073741824  # 1GB instead of default

# Reduce Grafana resources
grafana:
  environment:
    - GF_DATABASE_MAX_IDLE_CONN=2
    - GF_DATABASE_MAX_OPEN_CONN=5
```

### For High-Throughput

```yaml
# Increase InfluxDB capacity
influxdb:
  environment:
    - INFLUXD_STORAGE_CACHE_MAX_MEMORY_SIZE=2147483648  # 2GB

# Increase Node-RED heap
nodered:
  environment:
    - NODE_OPTIONS=--max-old-space-size=4096
```

## Security Hardening

### For Production Deployment

1. **Change Default Passwords**:
   - Grafana: Change admin password
   - InfluxDB: Update token and credentials
   - Secure Node-RED: Enable authentication

2. **Enable HTTPS**:
   - Add SSL certificates
   - Configure reverse proxy (nginx/traefik)

3. **Network Isolation**:
   - Use internal Docker networks
   - Expose only necessary ports
   - Configure firewall rules

4. **Authentication**:
   - Enable Mosquitto authentication
   - Add API authentication (JWT)
   - Configure Ditto policies properly

## Next Steps

After successful setup:

1. **Explore Grafana**: View dashboards and customize
2. **Test API**: Use cURL or Postman to explore endpoints
3. **Run Scenarios**: Test different failure modes
4. **Customize**: Adjust thresholds and parameters
5. **Integrate**: Connect to your existing systems

## Support Resources

- **Documentation**: See docs/ folder
- **Architecture**: ARCHITECTURE.md
- **API Reference**: docs/API.md
- **Predictive Maintenance**: docs/PREDICTIVE_MAINTENANCE.md
- **Issues**: Check Docker logs and test scripts

## Quick Reference Commands

```bash
# Start system
docker-compose up -d

# View logs
docker-compose logs -f

# Check status
docker ps

# Run simulator
python simulator/sensor_simulator.py

# Run tests
./tests/test-system.ps1  # Windows
./tests/test-api.sh      # Linux/Mac

# Stop system
docker-compose down

# Access Grafana
open http://localhost:3000

# Access Node-RED
open http://localhost:1880

# Test API
curl http://localhost:3001/api/health
```

---

**Setup Complete!** You should now have a fully functional Smart Cold Storage Digital Twin system running.
