#!/usr/bin/env python3
"""Audits the autonomous free-source PROP HUNTER installation."""
from __future__ import annotations
import importlib.util
import os
from pathlib import Path
from prop_hunter_shared_utils import hash_key, log, now_iso, safe_json_write, upsert_rows

FILES = [
    "prophunter.py", "prophunter_results.py", "prop_hunter_source_catalog.py",
    "prop_hunter_source_orchestrator.py", "prop_hunter_source_hub.py",
    "prop_hunter_browser_bookies.py", "prop_hunter_autolearn.py",
    "prop_hunter_builder_learning.py", "prop_hunter_builder_engine.py",
    "prop_hunter_odds_pp_ud.py", "prop_hunter_scraper.py",
    "prop_hunter_history_scraper.py", "prop_hunter_feature_builder.py",
    "prop_hunter_source_reliability.py", "prop_hunter_github_source_scanner.py",
    "prop_hunter_web_source_scanner.py", "prop_hunter_candidate_tester.py",
    ".github/workflows/prophunter.yml", ".github/workflows/prophunter_results.yml",
    ".github/workflows/prop_hunter_maintenance.yml", "requirements.txt",
]
REQUIRED_SECRETS = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "SUPABASE_URL", "SUPABASE_KEY"]
OPTIONAL_SECRETS = ["GEMINI_API_KEY", "GEMINI_API_KEYS", "GROQ_API_KEY", "GROQ_API_KEYS", "BALLDONTLIE_API_KEY", "ODDSPAPI_KEY", "ODDSPAPI", "GITHUB_TOKEN"]
PACKAGES = ["requests", "pandas", "supabase", "nba_api", "nflreadpy", "pybaseball", "bs4", "rapidfuzz", "pydantic", "playwright", "sklearn"]


def main():
    rows=[]; report={"created_at":now_iso(),"files":{},"required_secrets":{},"optional_secrets":{},"packages":{}}
    for f in FILES:
        ok=Path(f).exists(); report["files"][f]=ok
        rows.append({"audit_id":hash_key("file",f),"section":"file","item_key":f,"status":"ok" if ok else "missing","payload":{"ok":ok},"updated_at":now_iso()})
    for s in REQUIRED_SECRETS:
        ok=bool(os.getenv(s,"").strip()); report["required_secrets"][s]=ok
        rows.append({"audit_id":hash_key("secret_required",s),"section":"required_secret","item_key":s,"status":"ok" if ok else "missing","payload":{"present":ok},"updated_at":now_iso()})
    for s in OPTIONAL_SECRETS:
        ok=bool(os.getenv(s,"").strip()); report["optional_secrets"][s]=ok
        rows.append({"audit_id":hash_key("secret_optional",s),"section":"optional_secret","item_key":s,"status":"ok" if ok else "optional_missing","payload":{"present":ok},"updated_at":now_iso()})
    for p in PACKAGES:
        ok=importlib.util.find_spec(p) is not None; report["packages"][p]=ok
        rows.append({"audit_id":hash_key("package",p),"section":"package","item_key":p,"status":"ok" if ok else "missing","payload":{"ok":ok},"updated_at":now_iso()})
    report["missing_files"]=[k for k,v in report["files"].items() if not v]
    report["missing_required_secrets"]=[k for k,v in report["required_secrets"].items() if not v]
    safe_json_write("prop_hunter_source_audit.json",report)
    db_rows = [{
        "source_name": r.get("item_key"), "sport": None, "check_type": r.get("section"),
        "status": r.get("status"), "message": None, "latency_ms": None,
        "raw": r.get("payload") or {},
    } for r in rows]
    upsert_rows("prop_hunter_source_audit", db_rows)
    log(f"source audit files_missing={len(report['missing_files'])} required_secrets_missing={len(report['missing_required_secrets'])}")

if __name__=="__main__": main()
