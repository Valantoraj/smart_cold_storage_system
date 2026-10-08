# Smart Cold Storage Digital Twin

## Food Quality Monitoring and Predictive Maintenance System

A comprehensive monitoring and predictive-maintenance system designed for refrigerated storage facilities. The system continuously collects environmental and equipment data from multiple cold-storage units, creates digital representations of each physical unit, stores historical measurements, visualizes live conditions and trends, and identifies abnormal behavior early.

## 🎯 Project Overview

The Smart Cold Storage Digital Twin helps operators:
- Understand the current condition of every storage unit in real-time
- Recognize developing problems before they become critical
- Receive maintenance notifications before equipment failure
- Monitor food storage conditions continuously
- Analyze historical trends and patterns

## 🏗️ Architecture

```
Sensors → MQTT/Mosquitto → Node-RED → InfluxDB + Eclipse Ditto → Grafana → Alerts → Email

Web Controller (port 8088) → MQTT → Node-RED → InfluxDB + Ditto → Grafana → Alerts → Email
```

### Technology Stack

| Technology | Role |
|-----------|------|
| **MQTT** | Lightweight communication protocol for sensor data |
| **Mosquitto** | MQTT message broker |
| **Node-RED** | Data processing, routing, condition logic, and orchestration |
| **InfluxDB** | Historical time-series data storage |
| **Eclipse Ditto** | Digital twin representation and current state management |
| **Grafana** | Visualization, dashboards, trends, and monitoring |
| **Web Controller** | Interactive web UI to control simulation, trigger scenarios, and visualize units in real-time |
| **REST API** | Programmatic interaction with services and digital twins |
| **Docker** | Containerized and reproducible deployment |

## 📊 System Inputs

| Input | Purpose | Example |
|-------|---------|---------|
| Temperature | Monitors refrigeration and food-storage conditions | 4.2 °C |
| Humidity | Monitors moisture-related storage conditions | 67% |
| Compressor Status | Shows whether refrigeration equipment is operating | ON |
| Energy Consumption | Identifies inefficient or abnormal equipment behavior | 2.3 kW |
| Storage Unit ID | Identifies the source cold-storage unit | CS-01 |
| Timestamp | Records when the measurement was generated | 2026-09-30 10:30:00 |

## 🔍 Core Concept: Digital Twin

A digital twin is a digital representation of a physical asset that is continuously updated using data from that asset. In this project, every physical cold-storage unit has a corresponding digital twin.

**Example Digital Twin (CS-01):**
- Storage Unit ID: CS-01
- Current Temperature: 4.2 °C
- Current Humidity: 67%
- Compressor Status: ON
- Current Energy Consumption: 2.3 kW
- Last Update Timestamp
- Current Operational Status

## 🚨 Abnormal Condition Detection

The system continuously evaluates:
- Temperature threshold violations
- Humidity out of range
- Continuously increasing temperature trends
- Abnormal compressor runtime patterns
- Unusual energy consumption

## 🔧 Predictive Maintenance

The system identifies developing equipment problems by analyzing multiple signals:

```
IF temperature is continuously increasing
AND compressor runtime is increasing
AND energy consumption is increasing
THEN generate predictive-maintenance warning
```

This rule-based approach provides early warnings before equipment failures occur.

## 🖥️ Web Controller

The web controller at `http://localhost:8088` is an interactive web application that replaces the plain CLI simulator with a visual control center.

### Features

- **Live unit visualization**: Three cold storage unit cards with animated temperature gauges, humidity bars, compressor status icons (spinning when ON), and energy meters
- **Scenario triggers**: Click any of 8 conditions per unit — normal, temperature rising, temperature fluctuating, high energy, humidity drift, equipment degradation, door open, compressor failure
- **Real-time feedback**: When you trigger a scenario, the unit's visual representation changes immediately — gauges shift, compressor behavior changes, energy meters react
- **Speed control**: Run the simulation at 1x, 2x, 5x, or 10x speed for faster testing
- **Live alert feed**: Alerts appear in a scrolling feed with severity badges and toast notifications
- **Sparkline charts**: Each unit shows a mini temperature trend of the last 30 readings
- **Health indicators**: Each unit shows a health badge (healthy / warning / critical) with live status dots

### How it works

```
Web Controller → MQTT → Node-RED → InfluxDB + Eclipse Ditto → Grafana → Email Alerts
```

The web controller publishes sensor data to the same MQTT topics as the CLI simulator. Everything downstream (Node-RED processing, InfluxDB storage, Ditto twin updates, condition detection, alerts, emails) works identically.

## 📁 Project Structure

```
smart_cooling/
├── docker-compose.yml              # Docker orchestration
├── README.md                       # This file
├── ARCHITECTURE.md                 # Detailed architecture documentation
├── mosquitto/
│   └── config/
│       └── mosquitto.conf         # MQTT broker configuration
├── nodered/
│   ├── flows.json                 # Node-RED flow definitions
│   └── settings.js                # Node-RED settings
├── influxdb/
│   └── init/
│       └── init-schema.iql        # InfluxDB initialization
├── ditto/
│   ├── policies/                  # Digital twin policies
│   └── things/                    # Digital twin definitions
├── grafana/
│   ├── dashboards/                # Monitoring dashboards
│   └── provisioning/              # Dashboard provisioning
├── simulator/
│   ├── sensor_simulator.py        # Sensor data simulation (CLI)
│   └── requirements.txt           # Python dependencies
├── webapp/
│   ├── app.py                     # Flask + SocketIO web controller
│   ├── Dockerfile                 # Web controller container
│   ├── templates/
│   │   └── index.html             # Interactive UI with live visualizations
│   └── requirements.txt           # Python dependencies
├── api/
│   ├── server.js                  # REST API server
│   └── package.json               # API dependencies
├── tests/
│   └── api_tests.sh               # cURL test scripts
└── docs/
    ├── SETUP.md                   # Setup instructions
    └── API.md                     # API documentation
```

## 🚀 Quick Start

### Prerequisites
- Docker and Docker Compose installed
- Python 3.8+ (for sensor simulator)
- 8GB RAM minimum, 16GB recommended

### 1. Start All Services

```bash
docker-compose up -d
```

Wait 2-5 minutes for all services to initialize.

### 2. Initialize Digital Twins

```bash
# Windows PowerShell
cd ditto
.\init-ditto.ps1

# Linux/Mac
cd ditto
chmod +x init-ditto.sh
./init-ditto.sh
```

### 3. Run the Simulation

**Option A: Interactive Web Controller (recommended)**

The web controller runs automatically inside Docker. Open:

```
http://localhost:8088
```

You can:
- View all 3 cold storage units with live animated gauges
- Trigger any of 8 scenarios per unit (normal, temp rising, door open, etc.)
- Control simulation speed (1x, 2x, 5x, 10x)
- See live alerts and toast notifications
- Start/stop the simulation

**Option B: CLI Simulator**

```bash
cd simulator
pip install -r requirements.txt
python sensor_simulator.py
```

### 4. Access the Services

- **Web Controller**: http://localhost:8088 (interactive simulation UI)
- **Grafana Dashboard**: http://localhost:3000 (admin / Valan@2005)
- **Node-RED Editor**: http://localhost:1880
- **InfluxDB UI**: http://localhost:8086 (admin / adminpass123)
- **REST API**: http://localhost:3001/api
- **Eclipse Ditto API**: http://localhost:8080

### 5. Run Tests

```bash
# Windows PowerShell
cd tests
.\test-system.ps1

# Linux/Mac
cd tests
chmod +x test-api.sh
./test-api.sh
```

### 6. View Dashboards

Open Grafana at http://localhost:3000 and navigate to "Cold Storage Overview" dashboard.

**Detailed setup instructions**: See [docs/SETUP.md](./docs/SETUP.md)

## 📖 Documentation

- [Architecture Details](./ARCHITECTURE.md)
- [Setup Guide](./docs/SETUP.md)
- [API Documentation](./docs/API.md)

## 🧪 Testing

Test the system using cURL:

```bash
# Check system health
curl http://localhost:3001/api/health

# List all storage units
curl http://localhost:3001/api/storage

# Check storage unit CS-01 digital twin (Ditto)
curl http://localhost:8080/api/2/things/org.eclipse.ditto:CS-01 -H "x-ditto-pre-authenticated: nginx:ditto"

# Get current status via REST API
curl http://localhost:3001/api/storage/CS-01

# Get historical data
curl http://localhost:3001/api/storage/CS-01/history?start=-24h

# Check web controller status
curl http://localhost:8088/api/status

# Get active alerts
curl http://localhost:3001/api/alerts?status=active
```

## 📈 Expected Outputs

- Live storage conditions for every storage unit
- Current machine/compressor status
- Temperature and humidity trends
- Energy consumption trends
- Digital twin state for each storage unit
- Abnormal condition alerts
- Predictive maintenance notifications
- Historical data for analysis and investigation

## 🔄 Operational Flow Example

**Normal Operation (CS-02):**
1. Web controller generates sensor readings for CS-02
2. Readings published to MQTT topic `coldstorage/CS-02/data`
3. Mosquitto receives the MQTT message
4. Node-RED processes and validates the message
5. Measurement written to InfluxDB for historical analysis
6. Node-RED updates CS-02 digital twin in Eclipse Ditto
7. Grafana displays current condition and historical trend

**Abnormal Detection:**
8. Operator clicks "Door Open" scenario on CS-02 in the web controller
9. Temperature begins increasing: 4.0°C → 4.5°C → 5.2°C → 6.1°C → 7.0°C
10. Compressor runtime and energy consumption increase
11. Condition-detection logic in Node-RED identifies abnormal behavior
12. Alert published to MQTT, stored in InfluxDB, and email sent to operator
13. Grafana dashboard shows the alert in real-time

## 🛠️ Maintenance

### Stop All Services
```bash
docker-compose down
```

### View Logs
```bash
docker-compose logs -f [service-name]
```

### Reset Data
```bash
docker-compose down -v
docker-compose up -d
```

## 📝 License

This project is for educational and demonstration purposes.

## 🤝 Contributing

This is a complete implementation of a Smart Cold Storage Digital Twin system for food quality monitoring and predictive maintenance.
