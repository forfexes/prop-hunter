#!/usr/bin/env python3
"""Audit PROP HUNTER 13.10.1 keyless-hardened production installation."""
from __future__ import annotations
import importlib.util, os
from pathlib import Path
from prop_hunter_shared_utils import hash_key, log, now_iso, safe_json_write, upsert_rows

RUNTIME="13.10.1-KEYLESS-HARDENED"
CRITICAL_FILES=[
    "prophunter.py","prophunter_core_1392.py","prophunter_core_1391.py","prophunter_results.py",
    "prop_hunter_runtime_guard.py","prop_hunter_hard_test.py","prop_hunter_market_regression_test.py",
    "prop_hunter_daily_control.py","prop_hunter_shared_utils.py",
    "prop_hunter_quote_guard.py","prop_hunter_keyless_books.py",
    "prop_hunter_source_catalog.py","prop_hunter_source_catalog_core_1392.py",
    "prop_hunter_source_orchestrator.py","prop_hunter_source_orchestrator_core_1392.py",
    "prop_hunter_source_manager.py","prop_hunter_sgo.py","prop_hunter_opticodds.py",
    "prop_hunter_oddsapi_io.py","prop_hunter_oddspapi.py","prop_hunter_kambi.py","prop_hunter_1xbet.py",
    "prop_hunter_propline.py","prop_hunter_parlayapi.py","prop_hunter_market_consensus.py",
    "prop_hunter_odds_pp_ud.py","prop_hunter_scraper.py","prop_hunter_scoring.py",
    "prop_hunter_builder_engine.py","prop_hunter_builder_learning.py","prop_hunter_identity_hub.py",
    "prop_hunter_results_mlb.py","prop_hunter_results_nba.py","prop_hunter_results_wnba.py",
    "prop_hunter_results_nfl.py","prop_hunter_results_nhl.py","prop_hunter_feature_builder.py",
    "prop_hunter_settler.py","prop_hunter_clv_engine.py","prop_hunter_learning_update.py",
    "prop_hunter_model_registry.py","prop_hunter_retrainer.py","prop_hunter_coverage_watchdog.py",
    "prop_hunter_market_discovery.py",".github/workflows/prophunter.yml",
    ".github/workflows/prophunter_results.yml",".github/workflows/prop_hunter_maintenance.yml",
    ".github/workflows/prop_hunter_daily_control.yml",
    "requirements.txt","requirements_results.txt",
]
REQUIRED_SECRETS=["TELEGRAM_BOT_TOKEN","TELEGRAM_CHAT_ID","SUPABASE_URL","SUPABASE_KEY"]
ODDS_PROVIDERS={
    "the_odds_api":("ODDS_API_KEY","ODDS_API_KEYS"),
    "sportsgameodds":("SPORTSGAMEODDS_KEY","SPORTSGAMEODDS_API_KEY"),
    "opticodds":("OPTICODDS_API_KEY","OPTICODDS_KEY"),
    "parlayapi":("PARLAY_API_KEY",),"propline":("PROPLINE_API_KEY",),
    "oddsapi_io":("ODDSAPI_IO_KEY","ODDS_API_IO_KEY"),"oddspapi":("ODDSPAPI_KEY","ODDSPAPI"),
}
KEYLESS_FALLBACKS={
    "draftkings_direct":True,"fanduel_direct":True,"bovada_direct":True,"betrivers_direct":True,
    "kambi":True,"1xbet":True,
}
REQUIRED_PACKAGES=["requests","pydantic","rapidfuzz","supabase","pandas","pyarrow","nba_api","nflreadpy","pybaseball","statsapi","sklearn","curl_cffi"]
def _present(k): return bool(os.getenv(k,"").strip())
def _row(section,key,status,payload): return {"audit_id":hash_key(section,key),"section":section,"item_key":key,"status":status,"payload":payload,"updated_at":now_iso()}
def main():
    rows=[]; report={"created_at":now_iso(),"runtime":RUNTIME,"critical_files":{},"required_secrets":{},"odds_providers":{},"keyless_fallbacks":dict(KEYLESS_FALLBACKS),"required_packages":{}}
    for path in CRITICAL_FILES:
        ok=Path(path).exists(); report["critical_files"][path]=ok; rows.append(_row("critical_file",path,"ok" if ok else "missing",{"ok":ok}))
    for secret in REQUIRED_SECRETS:
        ok=_present(secret); report["required_secrets"][secret]=ok; rows.append(_row("required_secret",secret,"ok" if ok else "missing",{"present":ok}))
    keyed=0
    for provider,aliases in ODDS_PROVIDERS.items():
        present=[x for x in aliases if _present(x)]; ok=bool(present); keyed+=int(ok)
        report["odds_providers"][provider]={"configured":ok,"aliases_present":present}
        rows.append(_row("odds_provider",provider,"ok" if ok else "not_configured",{"configured":ok,"aliases_present":present}))
    for source,ok in KEYLESS_FALLBACKS.items(): rows.append(_row("keyless_source",source,"enabled" if ok else "disabled",{"enabled":ok}))
    report["live_odds_mode"]="keyless_plus_keyed" if keyed else "keyless_only"
    for pkg in REQUIRED_PACKAGES:
        ok=importlib.util.find_spec(pkg) is not None; report["required_packages"][pkg]=ok; rows.append(_row("required_package",pkg,"ok" if ok else "missing",{"ok":ok}))
    report["missing_critical_files"]=[k for k,v in report["critical_files"].items() if not v]
    report["missing_required_secrets"]=[k for k,v in report["required_secrets"].items() if not v]
    report["missing_required_packages"]=[k for k,v in report["required_packages"].items() if not v]
    report["ready"]=not(report["missing_critical_files"] or report["missing_required_secrets"] or report["missing_required_packages"])
    safe_json_write("prop_hunter_source_audit.json",report)
    upsert_rows("prop_hunter_source_audit",[{"source_name":r["item_key"],"sport":None,"check_type":r["section"],"status":r["status"],"message":None,"latency_ms":None,"raw":r["payload"]} for r in rows])
    log(f"source audit runtime={RUNTIME} ready={report['ready']} keyed_odds={keyed} keyless={len(KEYLESS_FALLBACKS)} mode={report['live_odds_mode']}")
if __name__=="__main__": main()
