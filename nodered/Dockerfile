FROM nodered/node-red:latest

# Install required custom nodes
RUN npm install --prefix /usr/src/node-red \
    node-red-contrib-influxdb@0.6.1 \
    node-red-dashboard@3.6.0 \
    @influxdata/influxdb-client@1.33.2 \
    node-red-node-email@2.0.0
