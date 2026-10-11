#!/usr/bin/env python3
import sys
sys.path.insert(0, '/tmp/gemini-venv/lib/python3.12/site-packages')

from google.cloud import bigquery

bq = bigquery.Client(project="project-f47e3be0-07f0-4225-b8e")
rows = list(bq.query("""
    SELECT run_id, trigger, llm_failed, model_used,
           ARRAY_LENGTH(units_evaluated) as units,
           TIMESTAMP_DIFF(completed_at, started_at, SECOND) as duration_s
    FROM `project-f47e3be0-07f0-4225-b8e.coldstorage.agent_runs`
    ORDER BY started_at DESC
    LIMIT 5
""").result())

print(f"=== agent_runs: {len(rows)} row(s) ===")
for r in rows:
    print(f"  run_id={r['run_id']}")
    print(f"    trigger={r['trigger']}  units={r['units']}  "
          f"llm_failed={r['llm_failed']}  model={r['model_used']}  "
          f"duration={r['duration_s']}s")

# Gate criteria
has_scheduler_run = any(r['trigger'] in ('scheduler','dry_run') for r in rows)
has_gemini_run    = any(r['model_used'] == 'gemini-3.5-flash' for r in rows)
has_3_units       = any(r['units'] == 3 for r in rows)

print("")
print("=== GATE G4c CHECKS ===")
print(f"  agent_runs rows exist:      {'PASS' if len(rows) > 0 else 'FAIL'}")
print(f"  scheduler/dry_run trigger:  {'PASS' if has_scheduler_run else 'FAIL'}")
print(f"  gemini-3.5-flash used:      {'PASS' if has_gemini_run else 'FAIL'}")
print(f"  3 units evaluated:          {'PASS' if has_3_units else 'FAIL'}")
print(f"  deterministic fallback:     {'PASS' if any(r['llm_failed'] for r in rows) else 'FAIL'}")

all_pass = len(rows) > 0 and has_scheduler_run and has_gemini_run and has_3_units
print("")
print(f"GATE G4c STATUS: {'PASS' if all_pass else 'FAIL'}")
