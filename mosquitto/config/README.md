# Mosquitto MQTT Broker Configuration

## Overview

This directory contains the configuration files for the Mosquitto MQTT broker used in the Smart Cold Storage Digital Twin system.

## Files

- **mosquitto.conf**: Main configuration file
- **acl.example**: Example Access Control List for topic-based authorization
- **passwd.example**: Example password file format

## MQTT Topic Structure

### Topic Hierarchy

```
coldstorage/
├── CS-01/
│   ├── data          # Sensor measurements (publish)
│   ├── status        # Unit status updates (publish)
│   ├── alerts        # Alert messages (subscribe/publish)
│   └── commands      # Control commands (subscribe)
├── CS-02/
│   ├── data
│   ├── status
│   ├── alerts
│   └── commands
└── CS-03/
    ├── data
    ├── status
    ├── alerts
    └── commands
```

### Topic Descriptions

| Topic Pattern | Purpose | Publisher | Subscriber |
|--------------|---------|-----------|------------|
| `coldstorage/+/data` | Sensor measurements | Sensors/Simulator | Node-RED, API |
| `coldstorage/+/status` | Unit operational status | Sensors/Simulator | Node-RED, Monitoring |
| `coldstorage/+/alerts` | Alert notifications | Node-RED | Dashboards, Alert Service |
| `coldstorage/+/commands` | Control commands | API, Dashboard | Sensors/Actuators |

### Wildcard Subscriptions

- `coldstorage/#` - Subscribe to all cold storage topics
- `coldstorage/+/data` - Subscribe to data from all units
- `coldstorage/CS-01/#` - Subscribe to all topics for unit CS-01

## Message Payload Format

### Data Message (coldstorage/CS-01/data)

```json
{
  "unitId": "CS-01",
  "temperature": 4.2,
  "humidity": 67,
  "compressorStatus": "ON",
  "energyConsumption": 2.3,
  "timestamp": "2026-10-05T10:30:00Z"
}
```

### Status Message (coldstorage/CS-01/status)

```json
{
  "unitId": "CS-01",
  "operational": true,
  "health": "healthy",
  "lastMaintenance": "2026-08-15",
  "timestamp": "2026-10-05T10:30:00Z"
}
```

### Alert Message (coldstorage/CS-01/alerts)

```json
{
  "unitId": "CS-01",
  "alertType": "temperature_high",
  "severity": "warning",
  "message": "Temperature exceeds threshold",
  "value": 8.5,
  "threshold": 8.0,
  "timestamp": "2026-10-05T10:30:00Z"
}
```

### Command Message (coldstorage/CS-01/commands)

```json
{
  "unitId": "CS-01",
  "command": "set_temperature",
  "parameters": {
    "target": 4.0
  },
  "timestamp": "2026-10-05T10:30:00Z"
}
```

## Security Configuration

### Enable Authentication

1. Create password file:
```bash
docker exec -it smart_cooling_mosquitto mosquitto_passwd -c /mosquitto/config/passwd username
```

2. Add more users:
```bash
docker exec -it smart_cooling_mosquitto mosquitto_passwd /mosquitto/config/passwd another_username
```

3. Update mosquitto.conf:
```conf
allow_anonymous false
password_file /mosquitto/config/passwd
```

4. Restart Mosquitto:
```bash
docker-compose restart mosquitto
```

### Enable Access Control

1. Copy and customize ACL file:
```bash
cp acl.example acl
```

2. Update mosquitto.conf:
```conf
acl_file /mosquitto/config/acl
```

3. Restart Mosquitto:
```bash
docker-compose restart mosquitto
```

## Testing MQTT

### Subscribe to Topics

```bash
# Subscribe to all data
docker exec -it smart_cooling_mosquitto mosquitto_sub -t "coldstorage/+/data" -v

# Subscribe to specific unit
docker exec -it smart_cooling_mosquitto mosquitto_sub -t "coldstorage/CS-01/#" -v

# Subscribe to all topics
docker exec -it smart_cooling_mosquitto mosquitto_sub -t "coldstorage/#" -v
```

### Publish Test Messages

```bash
# Publish sensor data
docker exec -it smart_cooling_mosquitto mosquitto_pub \
  -t "coldstorage/CS-01/data" \
  -m '{"unitId":"CS-01","temperature":4.2,"humidity":67,"compressorStatus":"ON","energyConsumption":2.3,"timestamp":"2026-10-05T10:30:00Z"}'

# Publish alert
docker exec -it smart_cooling_mosquitto mosquitto_pub \
  -t "coldstorage/CS-01/alerts" \
  -m '{"unitId":"CS-01","alertType":"temperature_high","severity":"warning","message":"Temperature exceeds threshold","value":8.5,"threshold":8.0,"timestamp":"2026-10-05T10:30:00Z"}'
```

### Using External MQTT Client

```bash
# Using mosquitto_pub (install mosquitto-clients)
mosquitto_pub -h localhost -p 1883 -t "coldstorage/CS-01/data" -m '{"unitId":"CS-01","temperature":4.2}'

# Using mosquitto_sub
mosquitto_sub -h localhost -p 1883 -t "coldstorage/#" -v
```

## QoS Levels

The system uses the following QoS (Quality of Service) levels:

- **QoS 0** (At most once): Fire and forget, fastest, no guarantee
- **QoS 1** (At least once): Guaranteed delivery, possible duplicates
- **QoS 2** (Exactly once): Guaranteed delivery once, slowest

### Recommended QoS by Topic

| Topic Type | QoS | Reason |
|-----------|-----|--------|
| data | 1 | Important measurements, allow duplicates |
| status | 1 | Important status updates |
| alerts | 2 | Critical alerts, no duplicates |
| commands | 2 | Critical commands, execute once |

## Performance Tuning

### For High-Frequency Data

If sending data every second from multiple units:

```conf
# Increase buffer sizes
max_queued_messages 5000
max_inflight_messages 50

# Adjust autosave
autosave_interval 300

# Increase connection limits
max_connections 1000
```

### For Low-Latency Requirements

```conf
# Reduce keepalive
max_keepalive 60

# Disable persistence for non-critical topics
# (requires selective topic configuration)
```

## Monitoring

### View Connected Clients

```bash
docker exec -it smart_cooling_mosquitto mosquitto_sub -t '$SYS/broker/clients/connected' -C 1
```

### View Total Messages

```bash
docker exec -it smart_cooling_mosquitto mosquitto_sub -t '$SYS/broker/messages/sent' -C 1
```

### View Uptime

```bash
docker exec -it smart_cooling_mosquitto mosquitto_sub -t '$SYS/broker/uptime' -C 1
```

### System Topics

Subscribe to all system topics:
```bash
docker exec -it smart_cooling_mosquitto mosquitto_sub -t '$SYS/#' -v
```

## Troubleshooting

### Check Logs

```bash
docker-compose logs mosquitto
```

### Verify Configuration

```bash
docker exec -it smart_cooling_mosquitto cat /mosquitto/config/mosquitto.conf
```

### Test Connection

```bash
docker exec -it smart_cooling_mosquitto mosquitto_sub -t '$SYS/broker/version' -C 1
```

### Permission Issues

If clients can't publish or subscribe:
1. Check ACL configuration
2. Verify user permissions
3. Check allow_anonymous setting
4. Review mosquitto logs for denied messages

## Production Recommendations

1. **Enable Authentication**: Set `allow_anonymous false`
2. **Configure ACL**: Restrict topic access per user/device
3. **Use TLS/SSL**: Enable encrypted connections
4. **Monitor Performance**: Watch $SYS topics for metrics
5. **Regular Backups**: Backup retained messages and persistence data
6. **Update Regularly**: Keep Mosquitto version current
7. **Rate Limiting**: Consider rate limits for high-frequency publishers
8. **Logging**: Configure appropriate log levels for production

## WebSocket Support

WebSocket is enabled on port 9001 for browser-based MQTT clients:

```javascript
// JavaScript example
const client = mqtt.connect('ws://localhost:9001');
client.subscribe('coldstorage/+/data');
client.on('message', (topic, message) => {
  console.log(topic, message.toString());
});
```

## References

- [Mosquitto Documentation](https://mosquitto.org/documentation/)
- [MQTT Protocol Specification](https://mqtt.org/)
- [MQTT QoS Explained](https://www.hivemq.com/blog/mqtt-essentials-part-6-mqtt-quality-of-service-levels/)
