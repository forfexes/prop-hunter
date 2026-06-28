from pathlib import Path
import os, importlib.util
from prop_hunter_shared_utils import safe_json_write, upsert_rows, hash_key, now_iso, log

FILES = [
"prophunter.py","prop_hunter_scraper.py","prop_hunter_scoring.py","prop_hunter_history_scraper.py",
"prop_hunter_backfill_universal.py","prop_hunter_shared_utils.py","prop_hunter_rules.py",
"prop_hunter_leg_builder.py","prop_hunter_learning.py","prop_hunter_settler.py",
"prop_hunter_learning_update.py","prop_hunter_clv_engine.py","prop_hunter_feature_builder.py",
"prop_hunter_social_signals.py","prop_hunter_github_source_scanner.py","prop_hunter_source_reliability.py",
"requirements.txt",".github/workflows/prophunter.yml"]
SECRETS = ["ODDS_API_KEY","ODDSAPI_IO_KEY","SPORTSGAMEODDS_API_KEY","OPTICODDS_API_KEY","ODDSPAPI",
"BALLDONTLIE_API_KEY","GEMINI_API_KEY","GROQ_API_KEY","TELEGRAM_BOT_TOKEN","TELEGRAM_CHAT_ID",
"SUPABASE_URL","SUPABASE_KEY","GITHUB_TOKEN","YOUTUBE_API_KEY","X_BEARER_TOKEN",
"INSTAGRAM_ACCESS_TOKEN","TIKTOK_RESEARCH_TOKEN","CFBD_API_KEY"]
PKGS = ["requests","pandas","supabase","nba_api","nflreadpy","pybaseball","bs4","rapidfuzz","pydantic"]

def pkg_ok(x): return importlib.util.find_spec(x) is not None

def main():
    rows=[]; report={"created_at":now_iso(),"files":{},"secrets":{},"packages":{}}
    for f in FILES:
        ok=Path(f).exists(); report["files"][f]=ok
        rows.append({"audit_id":hash_key("file",f),"section":"file","item_key":f,"status":"ok" if ok else "missing","payload":{"ok":ok},"updated_at":now_iso()})
    for s in SECRETS:
        ok=bool(os.getenv(s,"").strip()); report["secrets"][s]=ok
        rows.append({"audit_id":hash_key("secret",s),"section":"secret","item_key":s,"status":"ok" if ok else "missing","payload":{"present":ok},"updated_at":now_iso()})
    for p in PKGS:
        ok=pkg_ok(p); report["packages"][p]=ok
        rows.append({"audit_id":hash_key("package",p),"section":"package","item_key":p,"status":"ok" if ok else "missing","payload":{"ok":ok},"updated_at":now_iso()})
    report["missing_files"]=[k for k,v in report["files"].items() if not v]
    report["missing_secrets"]=[k for k,v in report["secrets"].items() if not v]
    safe_json_write("prop_hunter_source_audit.json",report)
    upsert_rows("prop_hunter_source_audit",rows,"audit_id")
    log(f"source audit done files_missing={len(report['missing_files'])} secrets_missing={len(report['missing_secrets'])}")

if __name__=="__main__": main()
