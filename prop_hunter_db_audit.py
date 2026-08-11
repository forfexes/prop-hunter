#!/usr/bin/env python3
"""Read-only Supabase health check for the active PROP HUNTER pipeline."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Dict

import requests

TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "20"))
REPORT = Path("prop_hunter_db_audit.json")

REQUIRED_SOURCE_TABLES = (
    "prop_hunter_prop_snapshots",
    "prop_hunter_source_audit",
    "prop_hunter_source_registry",
)
OPTIONAL_TABLES = (
    "prop_hunter_player_gamelogs",
    "prop_hunter_results",
    "prop_hunter_source_snapshots",
)
PICK_TABLES = ("prop_picks", "prop_hunter_picks")


def check_table(url: str, key: str, table: str) -> Dict[str, object]:
    try:
        response = requests.get(
            f"{url.rstrip('/')}/rest/v1/{table}",
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Accept": "application/json",
            },
            params={"select": "*", "limit": "1"},
            timeout=TIMEOUT,
        )
        return {
            "table": table,
            "ok": response.status_code == 200,
            "status": response.status_code,
            "sample_rows": len(response.json()) if response.status_code == 200 and isinstance(response.json(), list) else None,
            "error": None if response.status_code == 200 else response.text[:300],
        }
    except Exception as exc:
        return {"table": table, "ok": False, "status": None, "sample_rows": None, "error": str(exc)[:300]}


def main() -> int:
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    if not url or not key:
        print("SUPABASE DATABASE AUDIT: skipped — secrets missing")
        return 0

    results = {
        table: check_table(url, key, table)
        for table in (*REQUIRED_SOURCE_TABLES, *PICK_TABLES, *OPTIONAL_TABLES)
    }
    source_ready = all(results[t]["ok"] for t in REQUIRED_SOURCE_TABLES)
    active_pick_tables = [t for t in PICK_TABLES if results[t]["ok"]]
    ready = source_ready and bool(active_pick_tables)

    report = {
        "ready": ready,
        "source_ready": source_ready,
        "active_pick_tables": active_pick_tables,
        "tables": results,
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    for table in (*REQUIRED_SOURCE_TABLES, *PICK_TABLES, *OPTIONAL_TABLES):
        row = results[table]
        status = "OK" if row["ok"] else f"MISSING/ERROR {row['status']}"
        print(f"Supabase {table}: {status}")

    if ready:
        print(f"SUPABASE DATABASE ACTIVE: sources=OK picks={','.join(active_pick_tables)}")
        return 0

    print("SUPABASE DATABASE NOT READY: required source tables or picks table missing")
    strict = os.getenv("PH_DB_AUDIT_STRICT", "0").strip().lower() in ("1", "true", "yes")
    return 1 if strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
