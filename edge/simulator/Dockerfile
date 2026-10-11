FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY sim/ ./sim/

ENV MQTT_HOST=localhost
ENV MQTT_PORT=1883
ENV SIM_INTERVAL_S=5
ENV UNITS=CS-01,CS-02,CS-03
ENV PYTHONUNBUFFERED=1

CMD ["python3", "-m", "sim.main"]
