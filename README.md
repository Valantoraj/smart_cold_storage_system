# Smart Cold Storage Digital Twin

## Food Quality Monitoring · Predictive Maintenance · Edge AI

A distributed IoT system for monitoring refrigerated storage facilities. Three cold storage units are monitored across multiple warehouse locations using MQTT, Eclipse Ditto digital twins, InfluxDB time-series storage, Node-RED edge processing, and a GCP-hosted agentic AI layer built with Google ADK and Gemini 2.0 Flash.

## Architecture

```
                    ┌─────────────────────────────────────────┐
                    │              GCP CLOUD                  │
                    │  ioFog Controller · Eclipse Ditto        │
                    │  BigQuery (TimesFM ML) · Vertex AI       │
                    │  Gemini 2.0 Flash (ADK Multi-Agent)     │
                    │  Pub/Sub · Cloud Scheduler · Looker     │
                    └──────────┬──────────┬───────────────────┘
                               │ outbound │ outbound
              ┌────────────────┘          └────────────────┐
              ▼                                             ▼
┌──────────────────────┐          ┌──────────────────────────┐
│  LAPTOP 1 (Alpha)    │          │  LAPTOP 2 (Beta)         │
│  CS-01, CS-02        │          │  CS-03                   │
│                      │          │                          │
│  ioFog Agent         │          │  ioFog Agent             │
│  Mosquitto           │          │  Mosquitto               │
│  Node-RED (5 flows)  │          │  Node-RED (5 flows)      │
│  InfluxDB (7-day)    │          │  InfluxDB (7-day)        │
│  Edge Anomaly Det.   │          │  Edge Anomaly Det.       │
│  Ditto Sync Agent    │          │  Ditto Sync Agent        │
│  BigQuery Streamer   │          │  BigQuery Streamer       │
│  Web Controller      │          │                          │
│  REST API            │          │                          │
└──────────────────────┘          └──────────────────────────┘
         │                                    │
         └──────────── ioFog ECN ──────────────┘
              encrypted message bus via GCP
```

## Technology Stack

| Technology | Role |
|-----------|------|
| **MQTT / Mosquitto** | Lightweight sensor data transport at edge |
| **Eclipse Ditto** | Digital twin registry with WebSocket live notifications + Connectivity API |
| **InfluxDB** | Time-series storage (edge: 7-day buffer, central: 90-day) |
| **Node-RED** | 5-flow edge pipeline: ingestion, adaptive thresholds, ioFog bus, predictive maintenance, anomaly webhook |
| **Eclipse ioFog** | Distributed edge orchestration across laptops on different LANs |
| **GCP BigQuery** | Permanent sensor data lake with TimesFM anomaly detection |
| **GCP Vertex AI** | Gemini 2.0 Flash with Google ADK multi-agent system |
| **GCP Pub/Sub** | Event-driven triggers for agent and anomaly detection |
| **Grafana** | Fleet-wide dashboards reading from InfluxDB + BigQuery |
| **Looker Studio** | Shareable no-login dashboard connected to BigQuery |
| **Docker** | Containerized deployment with profile-based multi-machine support |

## Quick Start

### Single Machine (current working setup)

```bash
docker compose up -d
# Wait 3 minutes
# Run: python simulator/sensor_simulator.py
```

Access: http://localhost:8088 (Web Controller) | http://localhost:3000 (Grafana)

### Multi-Machine Distributed

**Laptop 1 (Warehouse Alpha — CS-01, CS-02):**
```powershell
.\setup.ps1 -Role alpha
```

**Laptop 2 (Warehouse Beta — CS-03):**
```powershell
.\setup.ps1 -Role beta
```

**Laptop 3 (Operations Console):**
```powershell
.\setup.ps1 -Role gamma
```

### GCP Setup (for cloud AI layer)

```bash
cd gcp
./setup.sh          # Creates BigQuery, Pub/Sub, Cloud Scheduler, ioFog VM
./central-services.sh  # Central InfluxDB + Grafana on GCP VM
```

## What Makes This Unique

1. **True distributed edge** — 3 laptops on different LANs, each operating independently offline
2. **Learning anomaly detection** — BigQuery ML TimesFM learns per-unit baselines, not static thresholds
3. **Conversational AI over real data** — Gemini agent with 9 tools answers questions grounded in actual SQL results
4. **Edge-cloud feedback loop** — Cloud ML scores calibrate edge detectors, improving accuracy over time
5. **Event-driven digital twins** — Ditto WebSocket pushes twin changes to UI, no polling
6. **Daily AI-generated reports** — Fleet Reporter sends Gemini-authored email at 7 AM

## Access Points

| Service | URL | Login |
|---------|-----|-------|
| Web Controller | http://localhost:8088 | — |
| Grafana | http://localhost:3000 | admin / Valan@2005 |
| Node-RED | http://localhost:1880 | — |
| InfluxDB | http://localhost:8086 | admin / adminpass123 |
| Ditto API | http://localhost:8080 | — |
| REST API | http://localhost:3001/api | — |
| AI Agent | http://localhost:9000 (Phase 6) | — |

## Documentation

- [Architecture](./ARCHITECTURE.md)
- [Setup Guide](./docs/SETUP.md)
- [API Reference](./docs/API.md)
- [Predictive Maintenance](./docs/PREDICTIVE_MAINTENANCE.md)
- [GCP Setup](./gcp/setup.sh)
- [ioFog Configuration](./iofog/)
- [Upgrade Plan](./UPGRADE_PLAN.txt)

## Project Structure

```
smart_cooling/
├── docker-compose.yml          # Profiles: single, alpha, beta, gamma
├── setup.ps1                   # One-command laptop setup
├── .env.example                # All config variables
├── UPGRADE_PLAN.txt            # Complete architecture roadmap
├── iofog/                      # Edge Compute Network
│   ├── controlplane.yaml       # GCP ioFog Controller
│   ├── agents.yaml             # 3 laptop agents
│   ├── routes.yaml             # 11 message bus routes
│   ├── apps/                   # Per-laptop microservice specs
│   └── microservices/          # Custom edge microservices
│       ├── edge-anomaly-detector/   # Z-score + correlation scoring
│       ├── ditto-sync-agent/        # Buffered twin sync with SQLite
│       ├── bigquery-streamer/       # Batch write + gap fill
│       └── fleet-reporter/          # Daily AI email report
├── gcp/                        # Google Cloud Platform
│   ├── setup.sh                # Full GCP provisioning
│   ├── central-services.sh     # Central InfluxDB + Grafana
│   ├── anomaly-runner.py       # BigQuery ML anomaly detection
│   ├── bigquery/               # Table schemas + SQL queries
│   └── agents/                 # ADK multi-agent system
│       ├── agent.py            # Root agent + Gemini function calling
│       ├── tools/              # BigQuery + Ditto tool definitions
│       └── Dockerfile
├── nodered/                    # 5-flow edge pipeline
├── webapp/                     # Interactive web controller
├── ditto/                      # Digital twin definitions + connectivity
├── influxdb/                   # Schemas + Flux queries
├── grafana/                    # Dashboards + provisioning
├── simulator/                  # Python sensor simulator
├── api/                        # REST API server
├── mosquitto/                  # MQTT broker config
└── docs/                       # Documentation
```

## License

For educational and demonstration purposes.
