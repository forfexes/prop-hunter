#!/usr/bin/env python3
"""Audit the current PROP HUNTER production installation.

This audit follows the V13.9.2 production graph instead of old V11/V13.5 files.
Browser packages are optional because normal card and maintenance runs explicitly
run with PH_BROWSER_ENABLED=0.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

from prop_hunter_shared_utils import hash_key, log, now_iso, safe_json_write, upsert_rows

CRITICAL_FILES = [
    "prophunter.py",
    "prophunter_core_1391.py",
    "prophunter_results.py",
    "prop_hunter_runtime_guard.py",
    "prop_hunter_shared_utils.py",
    "prop_hunter_source_catalog.py",
    "prop_hunter_source_orchestrator.py",
    "prop_hunter_source_manager.py",
    "prop_hunter_sgo.py",
    "prop_hunter_oddsapi_io.py",
    "prop_hunter_oddspapi.py",
    "prop_hunter_kambi.py",
    "prop_hunter_odds_pp_ud.py",
    "prop_hunter_scraper.py",
    "prop_hunter_scoring.py",
    "prop_hunter_builder_engine.py",
    "prop_hunter_builder_learning.py",
    "prop_hunter_identity_hub.py",
    "prop_hunter_results_mlb.py",
    "prop_hunter_results_nba.py",
    "prop_hunter_results_wnba.py",
    "prop_hunter_results_nfl.py",
    "prop_hunter_results_nhl.py",
    "prop_hunter_feature_builder.py",
    "prop_hunter_settler.py",
    "prop_hunter_clv_engine.py",
    "prop_hunter_learning_update.py",
    "prop_hunter_model_registry.py",
    "prop_hunter_retrainer.py",
    "prop_hunter_coverage_watchdog.py",
    "prop_hunter_market_discovery.py",
    "prop_hunter_github_watcher.py",
    ".github/workflows/prophunter.yml",
    ".github/workflows/prophunter_results.yml",
    ".github/workflows/prop_hunter_maintenance.yml",
    ".github/workflows/prop_hunter_github_watcher.yml",
    "requirements.txt",
    "requirements_results.txt",
]

SUPPORT_FILES = [
    "prop_hunter_browser_bookies.py",
    "prop_hunter_bet365.py",
    "prop_hunter_db_audit.py",
    "prop_hunter_odds_diagnostic.py",
    "prop_hunter_history_scraper.py",
    "prop_hunter_backfill_ncaaf.py",
    "prop_hunter_backfill_universal.py",
    "prop_hunter_retrosheet_import.py",
    "prop_hunter_statcast_backfill.py",
    "prop_hunter_social_signals.py",
    "requirements_browser.txt",
]

REQUIRED_SECRETS = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "SUPABASE_URL", "SUPABASE_KEY"]
ODDS_PROVIDERS = {
    "the_odds_api": ("ODDS_API_KEY", "ODDS_API_KEYS"),
    "sportsgameodds": ("SPORTSGAMEODDS_KEY", "SPORTSGAMEODDS_API_KEY"),
    "oddsapi_io": ("ODDSAPI_IO_KEY", "ODDS_API_IO_KEY"),
    "oddspapi": ("ODDSPAPI_KEY", "ODDSPAPI"),
}
OPTIONAL_SECRETS = [
    "GEMINI_API_KEY", "GROQ_API_KEY", "BALLDONTLIE_API_KEY", "GITHUB_TOKEN",
    "YOUTUBE_API_KEY", "X_BEARER_TOKEN",
]
REQUIRED_PACKAGES = [
    "requests", "pydantic", "rapidfuzz", "supabase", "pandas", "pyarrow",
    "nba_api", "nflreadpy", "pybaseball", "statsapi", "sklearn", "curl_cffi",
]
OPTIONAL_PACKAGES = ["playwright", "cloudscraper"]


def _present(name: str) -> bool:
    return bool(os.getenv(name, "").strip())


def _row(section: str, key: str, status: str, payload: dict) -> dict:
    return {
        "audit_id": hash_key(section, key),
        "section": section,
        "item_key": key,
        "status": status,
        "payload": payload,
        "updated_at": now_iso(),
    }


def main() -> None:
    rows = []
    report = {
        "created_at": now_iso(),
        "runtime": "13.9.2-HARDENED-SOURCES-SETTLEMENT",
        "critical_files": {},
        "support_files": {},
        "required_secrets": {},
        "odds_providers": {},
        "optional_secrets": {},
        "required_packages": {},
        "optional_packages": {},
    }

    for path in CRITICAL_FILES:
        ok = Path(path).exists()
        report["critical_files"][path] = ok
        rows.append(_row("critical_file", path, "ok" if ok else "missing", {"ok": ok}))

    for path in SUPPORT_FILES:
        ok = Path(path).exists()
        report["support_files"][path] = ok
        rows.append(_row("support_file", path, "ok" if ok else "optional_missing", {"ok": ok}))

    for secret in REQUIRED_SECRETS:
        ok = _present(secret)
        report["required_secrets"][secret] = ok
        rows.append(_row("required_secret", secret, "ok" if ok else "missing", {"present": ok}))

    configured_odds = 0
    for provider, aliases in ODDS_PROVIDERS.items():
        present_aliases = [name for name in aliases if _present(name)]
        ok = bool(present_aliases)
        configured_odds += int(ok)
        report["odds_providers"][provider] = {"configured": ok, "aliases_present": present_aliases}
        rows.append(_row(
            "odds_provider", provider, "ok" if ok else "not_configured",
            {"configured": ok, "aliases_present": present_aliases},
        ))

    report["live_odds_mode"] = "keyed_sources_available" if configured_odds else "kambi_fallback_only"
    rows.append(_row(
        "odds_provider_summary", "live_odds",
        "ok" if configured_odds else "fallback_only",
        {"configured_keyed_providers": configured_odds, "kambi_keyless_fallback": True},
    ))

    for secret in OPTIONAL_SECRETS:
        ok = _present(secret)
        report["optional_secrets"][secret] = ok
        rows.append(_row("optional_secret", secret, "ok" if ok else "optional_missing", {"present": ok}))

    for package in REQUIRED_PACKAGES:
        ok = importlib.util.find_spec(package) is not None
        report["required_packages"][package] = ok
        rows.append(_row("required_package", package, "ok" if ok else "missing", {"ok": ok}))

    for package in OPTIONAL_PACKAGES:
        ok = importlib.util.find_spec(package) is not None
        report["optional_packages"][package] = ok
        rows.append(_row("optional_package", package, "ok" if ok else "optional_missing", {"ok": ok}))

    report["missing_critical_files"] = [k for k, v in report["critical_files"].items() if not v]
    report["missing_required_secrets"] = [k for k, v in report["required_secrets"].items() if not v]
    report["missing_required_packages"] = [k for k, v in report["required_packages"].items() if not v]
    report["ready"] = not (
        report["missing_critical_files"]
        or report["missing_required_secrets"]
        or report["missing_required_packages"]
    )

    safe_json_write("prop_hunter_source_audit.json", report)
    db_rows = [{
        "source_name": r["item_key"],
        "sport": None,
        "check_type": r["section"],
        "status": r["status"],
        "message": None,
        "latency_ms": None,
        "raw": r["payload"],
    } for r in rows]
    upsert_rows("prop_hunter_source_audit", db_rows)
    log(
        "source audit ready=%s critical_missing=%d required_secrets_missing=%d "
        "required_packages_missing=%d keyed_odds=%d mode=%s"
        % (
            report["ready"], len(report["missing_critical_files"]),
            len(report["missing_required_secrets"]), len(report["missing_required_packages"]),
            configured_odds, report["live_odds_mode"],
        )
    )


if __name__ == "__main__":
    main()
