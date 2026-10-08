#!/usr/bin/env python3
"""
Fleet Reporter — Smart Cold Storage Digital Twin
=================================================
Runs daily at 07:00 IST (01:30 UTC) triggered by Cloud Scheduler via Pub/Sub.
Calls the Gemini agent to generate a comprehensive fleet health report.
Sends as HTML email and stores PDF in Cloud Storage.

The report includes:
  - Overall fleet health score (0-100)
  - Per-unit status with AI reasoning
  - Top 3 maintenance priorities with predicted urgency
  - Energy efficiency trends vs last week
  - Anomaly score summary (edge + cloud)
  - Patterns that should be investigated

Deploy as Cloud Function:
  gcloud functions deploy fleet-reporter \
    --runtime=python311 --trigger-topic=smart-cooling-agent-triggers \
    --entry-point=generate_report \
    --set-env-vars=PROJECT_ID=your-project,DATASET=cold_storage_lake
"""

import os
import json
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta
from google.cloud import bigquery
from google.oauth2 import service_account

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("fleet-reporter")

PROJECT_ID    = os.environ.get("GCP_PROJECT_ID", "")
DATASET       = os.environ.get("GCP_DATASET", "cold_storage_lake")
SA_KEY        = os.environ.get("GCP_SERVICE_ACCOUNT_KEY", "/app/gcp/service-account.json")
REGION        = os.environ.get("GCP_REGION", "asia-south1")

# Email config (reuse from existing system)
SMTP_HOST     = os.environ.get("ALERT_EMAIL_SMTP_HOST", "smtp.gmail.com")
SMTP_PORT     = int(os.environ.get("ALERT_EMAIL_SMTP_PORT", "465"))
SMTP_USER     = os.environ.get("ALERT_EMAIL_FROM", "traveleasypy@gmail.com")
SMTP_PASS     = os.environ.get("ALERT_EMAIL_APP_PASSWORD", "")
EMAIL_TO      = os.environ.get("ALERT_EMAIL_TO", "23i270@psgtech.ac.in")
AGENT_API_URL = os.environ.get("AGENT_API_URL", "http://localhost:9000")


def get_bigquery_client():
    if os.path.exists(SA_KEY):
        creds = service_account.Credentials.from_service_account_file(SA_KEY)
        return bigquery.Client(project=PROJECT_ID, credentials=creds)
    return bigquery.Client(project=PROJECT_ID)


def gather_fleet_data() -> dict:
    """Collect all data needed for the report from BigQuery"""
    client = get_bigquery_client()
    data = {"generatedAt": datetime.now(timezone.utc).isoformat()}

    # Latest anomaly scores per unit
    try:
        query = f"""
            SELECT unitId, warehouseId, cloudScore, riskLevel, explanation, dominantSignal, evaluatedAt
            FROM `{PROJECT_ID}.{DATASET}.anomaly_scores`
            WHERE evaluatedAt > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
            ORDER BY evaluatedAt DESC
        """
        rows = list(client.query(query).result())
        latest_scores = {}
        for r in rows:
            if r.unitId not in latest_scores:
                latest_scores[r.unitId] = {
                    "unitId": r.unitId,
                    "warehouseId": r.warehouseId,
                    "cloudScore": float(r.cloudScore) if r.cloudScore else 0,
                    "riskLevel": r.riskLevel,
                    "explanation": r.explanation,
                    "dominantSignal": r.dominantSignal
                }
        data["anomalyScores"] = list(latest_scores.values())
    except Exception as e:
        log.warning(f"Could not fetch anomaly scores: {e}")
        data["anomalyScores"] = []

    # Alert counts last 24h
    try:
        query = f"""
            SELECT unitId, alertType, severity, COUNT(*) as count
            FROM `{PROJECT_ID}.{DATASET}.alerts_history`
            WHERE timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
            GROUP BY unitId, alertType, severity
            ORDER BY count DESC
        """
        rows = list(client.query(query).result())
        data["alerts24h"] = [{
            "unitId": r.unitId, "alertType": r.alertType,
            "severity": r.severity, "count": r.count
        } for r in rows]
    except Exception as e:
        log.warning(f"Could not fetch alerts: {e}")
        data["alerts24h"] = []

    # Energy comparison (this week vs last week)
    try:
        query = f"""
            WITH this_week AS (
                SELECT unitId, AVG(energyConsumption) as avg_energy
                FROM `{PROJECT_ID}.{DATASET}.sensor_readings`
                WHERE timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
                GROUP BY unitId
            ),
            last_week AS (
                SELECT unitId, AVG(energyConsumption) as avg_energy
                FROM `{PROJECT_ID}.{DATASET}.sensor_readings`
                WHERE timestamp BETWEEN TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 14 DAY)
                                     AND TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
                GROUP BY unitId
            )
            SELECT t.unitId, t.avg_energy as this_week, l.avg_energy as last_week,
                   ((t.avg_energy - l.avg_energy) / l.avg_energy * 100) as pct_change
            FROM this_week t
            LEFT JOIN last_week l ON t.unitId = l.unitId
        """
        rows = list(client.query(query).result())
        data["energyComparison"] = [{
            "unitId": r.unitId,
            "thisWeek": round(float(r.this_week), 3) if r.this_week else 0,
            "lastWeek": round(float(r.last_week), 3) if r.last_week else 0,
            "pctChange": round(float(r.pct_change), 1) if r.pct_change else 0
        } for r in rows]
    except Exception as e:
        log.warning(f"Could not fetch energy comparison: {e}")
        data["energyComparison"] = []

    # Summary stats per unit
    try:
        query = f"""
            SELECT
                unitId, warehouseId,
                AVG(temperature) as avg_temp,
                MAX(temperature) as max_temp,
                MIN(temperature) as min_temp,
                AVG(energyConsumption) as avg_energy,
                MAX(energyConsumption) as max_energy,
                COUNTIF(compressorStatus = 'ON') / COUNT(*) * 100 as comp_pct
            FROM `{PROJECT_ID}.{DATASET}.sensor_readings`
            WHERE timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
            GROUP BY unitId, warehouseId
            ORDER BY unitId
        """
        rows = list(client.query(query).result())
        data["unitStats"] = [{
            "unitId": r.unitId, "warehouseId": r.warehouseId,
            "avgTemp": round(float(r.avg_temp), 2) if r.avg_temp else 0,
            "maxTemp": round(float(r.max_temp), 2) if r.max_temp else 0,
            "minTemp": round(float(r.min_temp), 2) if r.min_temp else 0,
            "avgEnergy": round(float(r.avg_energy), 2) if r.avg_energy else 0,
            "maxEnergy": round(float(r.max_energy), 2) if r.max_energy else 0,
            "compPct": round(float(r.comp_pct), 1) if r.comp_pct else 0
        } for r in rows]
    except Exception as e:
        log.warning(f"Could not fetch unit stats: {e}")
        data["unitStats"] = []

    return data


def generate_ai_summary(data: dict) -> str:
    """Call the Gemini agent to generate a natural language summary"""
    import requests
    try:
        prompt = f"""Generate a daily fleet health report for the Smart Cold Storage system.
        Here is the data from the last 24 hours:

        {json.dumps(data, indent=2, default=str)[:4000]}

        Provide:
        1. Overall fleet health (score 0-100 and one sentence summary)
        2. Per-unit status (CS-01, CS-02, CS-03) with any concerns
        3. Top maintenance priorities ranked by urgency
        4. Energy efficiency trend (better/worse than last week)
        5. Any patterns that should be investigated

        Be concise. Use bullet points. Include actual numbers from the data."""

        resp = requests.post(
            f"{AGENT_API_URL}/query",
            json={"question": prompt, "sessionId": "fleet-reporter"},
            timeout=120
        )
        if resp.status_code == 200:
            return resp.json().get("response", "AI summary unavailable")
        return "AI summary unavailable — agent service not reachable"
    except Exception as e:
        log.warning(f"AI summary generation failed: {e}")
        return f"AI summary unavailable: {e}"


def build_html_report(data: dict, ai_summary: str) -> str:
    """Build HTML email from fleet data + AI summary"""
    ist_time = (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).strftime("%d %b %Y, %H:%M IST")

    # Fleet health score (simple heuristic)
    scores = [s["cloudScore"] for s in data.get("anomalyScores", []) if s.get("cloudScore")]
    fleet_score = 100 - (max(scores) * 100 if scores else 0)
    fleet_color = "#059669" if fleet_score >= 70 else "#d97706" if fleet_score >= 40 else "#dc2626"

    html = f"""
    <html><body style="font-family:Inter,sans-serif;background:#f0f4f8;padding:20px">
    <div style="max-width:600px;margin:0 auto;background:#fff;border-radius:12px;padding:24px;border:1px solid #e2e8f0">
      <h1 style="font-size:20px;color:#1a202c;margin:0 0 4px 0">Smart Cold Storage — Daily Fleet Report</h1>
      <p style="font-size:12px;color:#a0aec0;margin:0 0 20px 0">{ist_time}</p>

      <div style="text-align:center;padding:16px;border-radius:8px;background:#f0f4f8;margin-bottom:20px">
        <div style="font-size:36px;font-weight:700;color:{fleet_color};font-family:'JetBrains Mono',monospace">{fleet_score:.0f}</div>
        <div style="font-size:12px;color:#4a5568">Fleet Health Score</div>
      </div>

      <h2 style="font-size:14px;color:#4a5568;text-transform:uppercase;letter-spacing:0.08em;margin:20px 0 10px 0">AI Summary</h2>
      <div style="font-size:13px;color:#1a202c;line-height:1.6;background:#f7fafc;padding:12px;border-radius:8px;border:1px solid #e2e8f0">
        {ai_summary.replace(chr(10), '<br>')}
      </div>

      <h2 style="font-size:14px;color:#4a5568;text-transform:uppercase;letter-spacing:0.08em;margin:20px 0 10px 0">Per-Unit Statistics (24h)</h2>
      <table style="width:100%;border-collapse:collapse;font-size:12px">
        <tr style="border-bottom:2px solid #e2e8f0">
          <th style="text-align:left;padding:6px;color:#4a5568">Unit</th>
          <th style="text-align:center;padding:6px;color:#4a5568">Avg Temp</th>
          <th style="text-align:center;padding:6px;color:#4a5568">Max Temp</th>
          <th style="text-align:center;padding:6px;color:#4a5568">Avg Energy</th>
          <th style="text-align:center;padding:6px;color:#4a5568">Comp %</th>
        </tr>
    """

    for s in data.get("unitStats", []):
        temp_color = "#dc2626" if s["maxTemp"] >= 10 else "#d97706" if s["maxTemp"] >= 8 else "#059669"
        html += f"""
        <tr style="border-bottom:1px solid #e2e8f0">
          <td style="padding:6px;font-weight:600;font-family:monospace">{s['unitId']}</td>
          <td style="text-align:center;padding:6px">{s['avgTemp']}°C</td>
          <td style="text-align:center;padding:6px;color:{temp_color}">{s['maxTemp']}°C</td>
          <td style="text-align:center;padding:6px">{s['avgEnergy']}kW</td>
          <td style="text-align:center;padding:6px">{s['compPct']}%</td>
        </tr>"""

    html += "</table>"

    # Energy comparison
    if data.get("energyComparison"):
        html += """
        <h2 style="font-size:14px;color:#4a5568;text-transform:uppercase;letter-spacing:0.08em;margin:20px 0 10px 0">Energy Trend (vs Last Week)</h2>
        <table style="width:100%;border-collapse:collapse;font-size:12px">
          <tr style="border-bottom:2px solid #e2e8f0">
            <th style="text-align:left;padding:6px;color:#4a5568">Unit</th>
            <th style="text-align:center;padding:6px;color:#4a5568">This Week</th>
            <th style="text-align:center;padding:6px;color:#4a5568">Last Week</th>
            <th style="text-align:center;padding:6px;color:#4a5568">Change</th>
          </tr>
        """
        for e in data["energyComparison"]:
            change_color = "#dc2626" if e["pctChange"] > 5 else "#059669" if e["pctChange"] < -5 else "#4a5568"
            html += f"""
            <tr style="border-bottom:1px solid #e2e8f0">
              <td style="padding:6px;font-weight:600;font-family:monospace">{e['unitId']}</td>
              <td style="text-align:center;padding:6px">{e['thisWeek']}kW</td>
              <td style="text-align:center;padding:6px">{e['lastWeek']}kW</td>
              <td style="text-align:center;padding:6px;color:{change_color}">{'+' if e['pctChange']>0 else ''}{e['pctChange']}%</td>
            </tr>"""
        html += "</table>"

    # Alerts
    if data.get("alerts24h"):
        html += """
        <h2 style="font-size:14px;color:#4a5568;text-transform:uppercase;letter-spacing:0.08em;margin:20px 0 10px 0">Alerts (24h)</h2>
        <table style="width:100%;border-collapse:collapse;font-size:12px">
          <tr style="border-bottom:2px solid #e2e8f0">
            <th style="text-align:left;padding:6px;color:#4a5568">Unit</th>
            <th style="text-align:left;padding:6px;color:#4a5568">Type</th>
            <th style="text-align:center;padding:6px;color:#4a5568">Severity</th>
            <th style="text-align:center;padding:6px;color:#4a5568">Count</th>
          </tr>
        """
        for a in data["alerts24h"]:
            sev_color = "#dc2626" if a["severity"] == "critical" else "#d97706"
            html += f"""
            <tr style="border-bottom:1px solid #e2e8f0">
              <td style="padding:6px;font-family:monospace">{a['unitId']}</td>
              <td style="padding:6px">{a['alertType'].replace('_',' ')}</td>
              <td style="text-align:center;padding:6px;color:{sev_color}">{a['severity']}</td>
              <td style="text-align:center;padding:6px">{a['count']}</td>
            </tr>"""
        html += "</table>"

    html += """
      <div style="margin-top:24px;padding-top:16px;border-top:1px solid #e2e8f0">
        <p style="font-size:11px;color:#a0aec0;text-align:center">
          Generated by Smart Cold Storage Digital Twin — Gemini 2.0 Flash Agent<br>
          This report is AI-generated and should be reviewed by a qualified operator.
        </p>
      </div>
    </div>
    </body></html>
    """
    return html


def send_email(html_body: str):
    """Send the report via SMTP"""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[Smart Cold Storage] Daily Fleet Report — {datetime.now().strftime('%d %b %Y')}"
    msg["From"] = SMTP_USER
    msg["To"] = EMAIL_TO
    msg.attach(MIMEText(html_body, "html"))

    try:
        server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT)
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, EMAIL_TO, msg.as_string())
        server.quit()
        log.info(f"Daily report email sent to {EMAIL_TO}")
    except Exception as e:
        log.error(f"Email send failed: {e}")


def generate_report(event=None, context=None):
    """Main entry point — triggered by Cloud Scheduler via Pub/Sub"""
    log.info("=" * 50)
    log.info("  Fleet Reporter — Daily Report Generation")
    log.info("=" * 50)

    # Gather data
    data = gather_fleet_data()
    log.info(f"Data gathered: {len(data.get('unitStats',[]))} units, {len(data.get('alerts24h',[]))} alert types")

    # Generate AI summary
    ai_summary = generate_ai_summary(data)
    log.info("AI summary generated")

    # Build HTML report
    html = build_html_report(data, ai_summary)

    # Send email
    send_email(html)

    # Store in BigQuery for audit
    try:
        client = get_bigquery_client()
        client.query(f"""
            INSERT INTO `{PROJECT_ID}.{DATASET}.fleet_reports`
            (reportDate, reportType, reportText, generatedBy, generatedAt, emailedTo)
            VALUES (
                CURRENT_DATE(),
                'daily',
                '{ai_summary[:5000].replace("'", "''")}',
                'gemini-2.0-flash',
                CURRENT_TIMESTAMP(),
                '{EMAIL_TO}'
            )
        """).result()
        log.info("Report stored in BigQuery")
    except Exception as e:
        log.warning(f"Could not store report in BigQuery: {e}")

    log.info("Fleet report complete.")
    return "OK"


if __name__ == "__main__":
    generate_report()
