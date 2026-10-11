# mosquitto-edge configuration template
# @FOG_HOST@ is replaced at container startup by entrypoint.sh

listener 1883 0.0.0.0
allow_anonymous true
persistence true
persistence_location /mosquitto/data/
max_queued_messages 200000
log_type error
log_type warning
log_type information

# Bridge to fog mosquitto
connection edge-to-fog
address @FOG_HOST@:1883
bridge_protocol_version mqttv311
cleansession false
local_clientid edge-bridge-l1
remote_clientid edge-l1-bridge
notifications false
restart_timeout 2 30
keepalive_interval 30
start_type automatic

# Outbound to fog: validated samples and edge alerts
topic coldstorage/+/validated out 1
topic coldstorage/+/edge_alert out 1

# Inbound from fog: control commands
topic coldstorage/+/control in 1
