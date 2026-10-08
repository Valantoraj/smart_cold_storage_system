#!/usr/bin/env python3
"""
Smart Cold Storage — Agentic AI System (Google ADK + Gemini)
=============================================================
Multi-agent system for cold storage fleet intelligence.
Built with Google Agent Development Kit (ADK) and Gemini 2.0 Flash.

Architecture:
  Root Agent: Fleet Intelligence Coordinator
    ├── Sub-Agent 1: Historical Analyst (BigQuery queries)
    ├── Sub-Agent 2: Digital Twin Inspector (Ditto API)
    ├── Sub-Agent 3: Anomaly Investigator (BigQuery ML scores)
    └── Sub-Agent 4: Maintenance Advisor (rankings + recommendations)

The root agent receives a question, decides which sub-agents to delegate to,
synthesizes their outputs, and returns a grounded response.

Deploy to Vertex AI Agent Engine:
  python agent.py --deploy

Run locally for development:
  python agent.py --serve

The Flask server (port 9000) exposes POST /query for the webapp to call.
"""

import os
import sys
import json
import logging
import argparse
from typing import Dict, Any

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("agent")

# ─── Tool imports ─────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))
from tools.bigquery_tools import (
    query_sensor_history, compute_trend, get_anomaly_scores,
    get_alert_history, compare_units, rank_units_by_maintenance_urgency
)
from tools.ditto_tools import (
    get_twin_state, get_all_twins_summary, get_maintenance_feature
)

PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "")
REGION     = os.environ.get("GCP_REGION", "asia-south1")
MODEL      = os.environ.get("GCP_MODEL", "gemini-2.0-flash-001")

# ─── Agent Definitions ────────────────────────────────────────────────────────

AGENT_INSTRUCTIONS = """You are the Fleet Intelligence Coordinator for a Smart Cold Storage Digital Twin system.
You monitor 3 cold storage units (CS-01, CS-02, CS-03) across multiple warehouses.

Your role:
1. Receive questions about the fleet's health, anomalies, and maintenance needs
2. Decide which specialized sub-agents or tools to call
3. Synthesize their outputs into a clear, actionable response

Rules:
- ALWAYS call tools to get real data before answering. Never hallucinate numbers.
- When asked about current state, use get_twin_state or get_all_twins_summary
- When asked about history or trends, use query_sensor_history or compute_trend
- When asked about anomalies, use get_anomaly_scores
- When asked about maintenance, use rank_units_by_maintenance_urgency
- When asked to compare units, use compare_units
- When asked about alerts, use get_alert_history
- Be specific: cite actual values, timestamps, and trends from tool results
- If data is unavailable, say so clearly rather than guessing
- Keep responses concise but thorough. Use bullet points for multiple findings.
"""


# ─── Tool schemas for Gemini function calling ─────────────────────────────────
TOOL_DEFINITIONS = [
    {
        "name": "query_sensor_history",
        "description": "Query historical sensor data for a specific unit and metric",
        "parameters": {
            "type": "object",
            "properties": {
                "unit_id": {"type": "string", "description": "Cold storage unit ID (CS-01, CS-02, CS-03)"},
                "metric": {"type": "string", "description": "Sensor metric: temperature, humidity, or energyConsumption"},
                "hours": {"type": "integer", "description": "Hours of history to retrieve (default 24)"}
            },
            "required": ["unit_id"]
        }
    },
    {
        "name": "compute_trend",
        "description": "Compute the trend (slope/direction) of a metric over a time window",
        "parameters": {
            "type": "object",
            "properties": {
                "unit_id": {"type": "string", "description": "Cold storage unit ID"},
                "metric": {"type": "string", "description": "Metric to analyze"},
                "window_hours": {"type": "integer", "description": "Time window in hours (default 6)"}
            },
            "required": ["unit_id"]
        }
    },
    {
        "name": "get_anomaly_scores",
        "description": "Retrieve BigQuery ML anomaly detection scores",
        "parameters": {
            "type": "object",
            "properties": {
                "unit_id": {"type": "string", "description": "Specific unit (optional — omit for all units)"},
                "hours": {"type": "integer", "description": "Hours of scores to retrieve (default 24)"}
            }
        }
    },
    {
        "name": "get_alert_history",
        "description": "Retrieve alert history for a specific unit",
        "parameters": {
            "type": "object",
            "properties": {
                "unit_id": {"type": "string", "description": "Cold storage unit ID"},
                "hours": {"type": "integer", "description": "Hours of alerts (default 24)"}
            },
            "required": ["unit_id"]
        }
    },
    {
        "name": "compare_units",
        "description": "Compare a metric across all cold storage units",
        "parameters": {
            "type": "object",
            "properties": {
                "metric": {"type": "string", "description": "Metric to compare"},
                "days": {"type": "integer", "description": "Days to include (default 7)"}
            }
        }
    },
    {
        "name": "rank_units_by_maintenance_urgency",
        "description": "Rank all units by maintenance urgency based on anomaly scores and alert frequency",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "get_twin_state",
        "description": "Get current digital twin state from Eclipse Ditto for a specific unit",
        "parameters": {
            "type": "object",
            "properties": {
                "unit_id": {"type": "string", "description": "Cold storage unit ID"}
            },
            "required": ["unit_id"]
        }
    },
    {
        "name": "get_all_twins_summary",
        "description": "Get a summary of all digital twins with health status",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "get_maintenance_feature",
        "description": "Get maintenance score and recommendation for a specific unit",
        "parameters": {
            "type": "object",
            "properties": {
                "unit_id": {"type": "string", "description": "Cold storage unit ID"}
            },
            "required": ["unit_id"]
        }
    }
]

# Map tool names to actual functions
TOOL_FUNCTIONS = {
    "query_sensor_history": query_sensor_history,
    "compute_trend": compute_trend,
    "get_anomaly_scores": get_anomaly_scores,
    "get_alert_history": get_alert_history,
    "compare_units": compare_units,
    "rank_units_by_maintenance_urgency": rank_units_by_maintenance_urgency,
    "get_twin_state": get_twin_state,
    "get_all_twins_summary": get_all_twins_summary,
    "get_maintenance_feature": get_maintenance_feature,
}


# ─── Gemini-based agent ──────────────────────────────────────────────────────
def query_agent(question: str, session_id: str = "default") -> Dict:
    """
    Process a natural language query using Gemini 2.0 Flash with function calling.
    
    The model decides which tools to call, we execute them, and feed results back
    for the model to synthesize into a final answer.
    """
    try:
        import vertexai
        from vertexai.generative_models import GenerativeModel, FunctionDeclaration, Tool

        vertexai.init(project=PROJECT_ID, location=REGION)
        model = GenerativeModel(MODEL, system_instruction=AGENT_INSTRUCTIONS)

        # Build function declarations
        func_decls = []
        for td in TOOL_DEFINITIONS:
            params = {}
            for key, val in td.get("parameters", {}).get("properties", {}).items():
                ptype = val.get("type", "string")
                params[key] = val.get("description", key)
            func_decls.append(FunctionDeclaration(
                name=td["name"],
                description=td["description"],
                parameters=params
            ))

        tools = [Tool(func_decls)]

        chat = model.start_chat(tools=tools)
        response = chat.send_message(question)

        # Handle function calling loop
        max_iterations = 10
        iterations = 0
        tool_calls_made = []

        while response.candidates and response.candidates[0].content and hasattr(response, 'function_calls'):
            func_calls = response.function_calls
            if not func_calls:
                break

            for fc in func_calls:
                func_name = fc.name
                func_args = fc.args or {}

                tool_calls_made.append({
                    "tool": func_name,
                    "args": dict(func_args)
                })

                # Execute the tool
                func = TOOL_FUNCTIONS.get(func_name)
                if func:
                    try:
                        result = func(**dict(func_args))
                        log.info(f"Tool {func_name} called with {func_args}")
                        # Feed result back to model
                        response = chat.send_message(
                            f"Tool {func_name} returned: {json.dumps(result, default=str)[:3000]}"
                        )
                    except Exception as e:
                        log.error(f"Tool {func_name} failed: {e}")
                        response = chat.send_message(f"Tool {func_name} error: {str(e)}")
                else:
                    response = chat.send_message(f"Unknown tool: {func_name}")

            iterations += 1
            if iterations >= max_iterations:
                response = chat.send_message("Please summarize your findings now.")
                break

        # Extract final text response
        final_text = ""
        if response.candidates and response.candidates[0].content:
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'text') and part.text:
                    final_text += part.text

        return {
            "response": final_text or "I could not generate a response. Please try again.",
            "toolCalls": tool_calls_made,
            "iterations": iterations,
            "model": MODEL,
            "status": "ok"
        }

    except ImportError:
        log.warning("vertexai not installed — returning fallback response")
        return {
            "response": "AI agent requires google-cloud-vertexai. Install with: pip install google-cloud-aiplatform",
            "toolCalls": [],
            "status": "dependency_missing"
        }
    except Exception as e:
        log.error(f"Agent query failed: {e}")
        return {
            "response": f"I encountered an error processing your request: {str(e)}",
            "toolCalls": [],
            "status": "error"
        }


# ─── Flask Server (for webapp integration) ─────────────────────────────────────
def run_server():
    from flask import Flask, request, jsonify
    app = Flask(__name__)

    @app.route("/query", methods=["POST"])
    def handle_query():
        body = request.get_json(silent=True) or {}
        question = body.get("question", "")
        session_id = body.get("sessionId", "default")

        if not question:
            return jsonify({"error": "No question provided"}), 400

        log.info(f"Query from {session_id}: {question[:100]}")
        result = query_agent(question, session_id)
        return jsonify(result)

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({
            "status": "ok",
            "model": MODEL,
            "project": PROJECT_ID,
            "tools": [td["name"] for td in TOOL_DEFINITIONS]
        })

    @app.route("/proactive-check", methods=["POST"])
    def proactive_check():
        """Run autonomous fleet health check (triggered by Cloud Scheduler)"""
        log.info("Proactive check triggered")
        result = query_agent(
            "Perform a proactive fleet health check. "
            "Get anomaly scores for all units, check twin states, "
            "and report any units with elevated risk. "
            "If all units are normal, say 'All units operating normally.'",
            "proactive"
        )
        return jsonify(result)

    log.info("=" * 55)
    log.info("  Smart Cold Storage AI Agent Service")
    log.info(f"  Model:    {MODEL}")
    log.info(f"  Project:  {PROJECT_ID}")
    log.info(f"  Region:   {REGION}")
    log.info(f"  Tools:    {len(TOOL_DEFINITIONS)}")
    log.info(f"  Port:     9000")
    log.info("=" * 55)
    app.run(host="0.0.0.0", port=9000, debug=False)


# ─── Deploy to Vertex AI Agent Engine ─────────────────────────────────────────
def deploy_to_vertex():
    try:
        import vertexai
        from vertexai.agent_engines import AdkApp

        vertexai.init(project=PROJECT_ID, location=REGION)

        log.info("Deploying agent to Vertex AI Agent Engine...")
        # The ADK AdkApp wraps our agent for the Agent Engine
        agent_engine = AdkApp(
            agent_func=query_agent,
            requirements=[
                "google-cloud-aiplatform>=1.74.0",
                "google-cloud-bigquery>=3.11.0",
                "requests>=2.31.0"
            ]
        )

        remote_app = agent_engine.deploy(
            display_name="smart-cold-storage-agent",
            description="Cold storage fleet intelligence agent with BigQuery + Ditto tools"
        )

        log.info(f"Deployed! Resource ID: {remote_app.resource_name}")
        log.info(f"Add to .env: GCP_AGENT_ENGINE_ID={remote_app.resource_name}")
        return remote_app.resource_name

    except ImportError:
        log.error("vertexai agent_engines not available. Install: pip install google-cloud-aiplatform")
        return None
    except Exception as e:
        log.error(f"Deploy failed: {e}")
        return None


# ─── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Smart Cold Storage AI Agent")
    parser.add_argument("--serve", action="store_true", help="Run Flask server locally")
    parser.add_argument("--deploy", action="store_true", help="Deploy to Vertex AI Agent Engine")
    parser.add_argument("--test", type=str, help="Test a single query")
    args = parser.parse_args()

    if args.deploy:
        deploy_to_vertex()
    elif args.test:
        result = query_agent(args.test)
        print(json.dumps(result, indent=2, default=str))
    else:
        run_server()
