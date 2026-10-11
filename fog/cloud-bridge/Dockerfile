FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bridge/ ./bridge/

RUN mkdir -p /data /secrets

ENV MQTT_HOST=mosquitto-fog
ENV MQTT_PORT=1883
ENV GCP_PROJECT_ID=project-f47e3be0-07f0-4225-b8e
ENV TOPIC=coldstorage-telemetry
ENV SUBSCRIPTION=agent-actions-sub
ENV OUTBOX_PATH=/data/outbox.db
ENV PYTHONUNBUFFERED=1

VOLUME ["/data", "/secrets"]

CMD ["python3", "-m", "bridge.main"]
