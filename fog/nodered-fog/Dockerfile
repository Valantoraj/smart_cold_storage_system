FROM nodered/node-red:4.0.5

USER root

WORKDIR /usr/src/node-red

COPY settings.js ./settings.js
COPY flows.json  ./flows.json
COPY lib/        ./lib/

# Copy shared config
COPY ../../config/rules.json ./config/rules.json 2>/dev/null || true
COPY ../../config/units.json ./config/units.json 2>/dev/null || true

ENV NODE_ENV=production
ENV FLOWS=flows.json
ENV FOG_NODE_ID=fog-l2

EXPOSE 1880

USER node-red
