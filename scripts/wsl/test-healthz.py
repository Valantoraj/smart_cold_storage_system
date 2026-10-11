#!/usr/bin/env python3
"""Test maintenance-agent endpoints using ADC access token."""
import sys
sys.path.insert(0, '/tmp/gemini-venv/lib/python3.12/site-packages')

import google.auth
import google.auth.transport.requests
import urllib.request
import json

creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
creds.refresh(google.auth.transport.requests.Request())
token = creds.token

BASE = "https://maintenance-agent-qkttklqguq-uc.a.run.app"
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

def get(path):
    req = urllib.request.Request(f"{BASE}{path}", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:100]

def post(path):
    req = urllib.request.Request(f"{BASE}{path}", data=b"{}", headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:100]

print("=== maintenance-agent endpoint tests (ADC access token) ===")
code, body = get("/healthz")
print(f"/healthz        -> HTTP {code}: {body[:100]}")

code, body = get("/last-run")
print(f"/last-run        -> HTTP {code}: {body[:120]}")

print("")
print("All tests done")
