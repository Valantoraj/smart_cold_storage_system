FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Copy service account key if available
COPY gcp/service-account.json /app/gcp/service-account.json

EXPOSE 9000

CMD ["python", "agent.py", "--serve"]
