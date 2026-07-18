#!/usr/bin/env python3
"""Fault-tolerant multi-source orchestrator for PROP HUNTER.

No single source can stop a run. Every result is normalized, cached, audited and
stored as a raw pre-game snapshot. The active card reads only fresh rows.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from prop_hunter_shared_utils import hash_key, now_iso, safe_json_load, safe_json_write, to_float, upsert_rows, warn
from prop_hunter_source_catalog import SOURCES, as_rows

SPORTS = tuple(x.strip().upper() for x in os.getenv("PROP_HUNTER_SPORTS", "MLB,WNBA,NBA,NFL").split(",") if x.strip())
CACHE_DIR = Path(os.getenv("PH_SOURCE_CACHE_DIR", ".prop_hunter_cache"))
OUT_FILE = Path(os.getenv("PH_SOURCE_OUTPUT", "prop_hunter_all_sources.json"))


def _row_key(row: Dict[str, Any]) -> str:
    return str(row.get("snapshot_id") or hash_key(
        row.get("source"), row.get("sport"), row.get("source_event_id") or row.get("game_id"),
        row.get("player_name"), row.get("market_key") or row.get("market"),
        row.get("direction"), row.get("line"), row.get("odds_decimal"),
        row.get("period"), row.get("is_live"),
    ))


def _normalise(row: Dict[str, Any], source: str) -> Optional[Dict[str, Any]]:
    if not isinstance(row, dict):
        return None
    player = row.get("player_name") or row.get("player")
    market = row.get("market_key") or row.get("market")
    line = row.get("line") if row.get("line") is not None else row.get("point")
    if not player or not market or line is None:
        return None
    out = dict(row)
    out["source"] = str(out.get("source") or source).lower()
    out["bookmaker"] = str(out.get("bookmaker") or out["source"]).lower()
    out["sport"] = str(out.get("sport") or out.get("league") or "").upper()
    out["league"] = str(out.get("league") or out.get("sport") or "").upper()
    out["direction"] = str(out.get("direction") or ("under" if "under" in str(out.get("market", "")).lower() else "over")).lower()
    out["snapshot_id"] = _row_key(out)
    out["created_at"] = out.get("created_at") or now_iso()
    out["raw"] = out.get("raw") if isinstance(out.get("raw"), dict) else {"raw": out.get("raw")}
    return out


def _cache_path(source: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{source}.json"


def _write_cache(source: str, rows: List[Dict[str, Any]]) -> None:
    if rows:
        safe_json_write(_cache_path(source), {"saved_at": now_iso(), "rows": rows})


def _read_cache(source: str, max_age_hours: float) -> List[Dict[str, Any]]:
    payload = safe_json_load(_cache_path(source), {}) or {}
    saved_at = payload.get("saved_at")
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(str(saved_at).replace("Z", "+00:00"))).total_seconds() / 3600
    except Exception:
        return []
    if age > max_age_hours:
        return []
    rows = payload.get("rows") or []
    for row in rows:
        row["cache_fallback"] = True
        row["cache_age_hours"] = round(age, 2)
    return rows


def _audit(source: str, status: str, rows: List[Dict[str, Any]], elapsed: float, error: str = "", cached: bool = False) -> Dict[str, Any]:
    odds_rows = sum(1 for r in rows if r.get("odds_decimal"))
    players = len({str(r.get("player_name") or "").lower() for r in rows if r.get("player_name")})
    sports = sorted({str(r.get("sport") or "") for r in rows if r.get("sport")})
    return {
        "audit_id": hash_key(source, datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")),
        "section": "source_health",
        "item_key": source,
        "status": status,
        "message": error[:500],
        "payload": {
            "rows": len(rows), "players": players, "odds_rows": odds_rows,
            "odds_coverage": round(odds_rows / max(1, len(rows)), 4),
            "sports": sports, "elapsed_s": round(elapsed, 2), "cached": cached,
        },
        "updated_at": now_iso(),
    }


def _call(source: str, fn: Callable[[], List[Dict[str, Any]]], max_cache_age: float) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    started = time.monotonic()
    error = ""
    try:
        raw = fn() or []
        rows = [x for x in (_normalise(r, source) for r in raw) if x]
    except Exception as exc:
        rows = []
        error = f"{type(exc).__name__}: {exc}"
    elapsed = time.monotonic() - started
    if rows:
        _write_cache(source, rows)
        return rows, _audit(source, "active", rows, elapsed, error)
    cached_rows = _read_cache(source, max_cache_age)
    if cached_rows:
        return cached_rows, _audit(source, "cached", cached_rows, elapsed, error or "live source empty", cached=True)
    return [], _audit(source, "blocked" if error else "empty", [], elapsed, error)


def _direct_jobs(sports: Iterable[str]) -> List[Tuple[str, Callable[[], List[Dict[str, Any]]]]]:
    import prop_hunter_odds_pp_ud as ppud
    jobs: List[Tuple[str, Callable[[], List[Dict[str, Any]]]]] = [
        ("underdog", ppud.fetch_underdog),
        ("sleeper", ppud.fetch_sleeper),
    ]
    for sport in sports:
        jobs.extend([
            (f"prizepicks_{sport.lower()}", lambda s=sport: ppud.fetch_prizepicks(s)),
            (f"draftkings_{sport.lower()}", lambda s=sport: ppud.fetch_draftkings(s)),
            (f"fanduel_{sport.lower()}", lambda s=sport: ppud.fetch_fanduel(s)),
            (f"bovada_{sport.lower()}", lambda s=sport: ppud.fetch_bovada(s)),
            (f"espn_bet_{sport.lower()}", lambda s=sport: ppud.fetch_espn_bet(s)),
        ])
    return jobs


def _browser_jobs(sports: Iterable[str], books: Iterable[str]) -> List[Tuple[str, Callable[[], List[Dict[str, Any]]]]]:
    from prop_hunter_browser_bookies import fetch_browser_source
    jobs: List[Tuple[str, Callable[[], List[Dict[str, Any]]]]] = []
    # Interleave books across active sports, so a small fast-job budget covers
    # MLB and WNBA instead of spending every browser attempt on one league.
    for book in books:
        for sport in sports:
            jobs.append((f"browser_{book}_{sport.lower()}", lambda b=book, s=sport: fetch_browser_source(b, s)[0]))
    return jobs


def _season_active_sports(sports: Iterable[str]) -> List[str]:
    month = datetime.now(timezone.utc).month
    active = []
    for sport in sports:
        if sport == "MLB" and 3 <= month <= 11:
            active.append(sport)
        elif sport == "WNBA" and 5 <= month <= 10:
            active.append(sport)
        elif sport == "NFL" and (month >= 8 or month <= 2):
            active.append(sport)
        elif sport == "NBA" and (month >= 10 or month <= 6):
            active.append(sport)
        elif sport == "NHL" and (month >= 10 or month <= 6):
            active.append(sport)
    return active or list(sports)




def _upsert_chunks(table: str, rows: List[Dict[str, Any]], conflict: Optional[str] = None, size: int = 250) -> None:
    for i in range(0, len(rows), size):
        upsert_rows(table, rows[i:i + size], conflict=conflict)

def persist_registry() -> None:
    rows = []
    for spec in as_rows():
        rows.append({
            "source_name": spec["key"], "source_type": spec["category"],
            "url": spec["homepage"], "sport": ",".join(spec["sports"]),
            "league": ",".join(spec["sports"]) or "ALL",
            "enabled": spec["active_by_default"], "priority": spec["priority"],
            "notes": spec["notes"],
            "raw": {"display_name": spec["name"], "access": spec["access"], "methods": list(spec["methods"])},
            "updated_at": now_iso(),
        })
    _upsert_chunks("prop_hunter_source_registry", rows, conflict="source_name", size=100)
    safe_json_write("prop_hunter_source_registry.json", rows)


def collect(sport_filter: Optional[str] = None, mode: str = "fast") -> List[Dict[str, Any]]:
    sports = [sport_filter.upper()] if sport_filter else list(SPORTS)
    sports = [s for s in sports if s in {"MLB", "NBA", "WNBA", "NFL", "NHL"}]
    max_cache_age = 8 if mode == "fast" else 30
    all_rows: List[Dict[str, Any]] = []
    audits: List[Dict[str, Any]] = []

    for source, fn in _direct_jobs(sports):
        rows, audit = _call(source, fn, max_cache_age)
        all_rows.extend(rows); audits.append(audit)
        print(f"source {source}: {len(rows)} | {audit['status']}", flush=True)

    direct_odds_rows = sum(1 for row in all_rows if to_float(row.get("odds_decimal")) and float(row.get("odds_decimal")) > 1)

    # Full browser sweep in data/maintenance mode. On a card run, activate a
    # small automatic browser fallback only when direct sources produced no
    # bookable prices.
    run_browser = mode in {"all", "browser"} or (mode == "fast" and direct_odds_rows == 0)
    if run_browser:
        if mode == "fast":
            books = [x.strip() for x in os.getenv(
                "PH_FAST_BROWSER_BOOKS", "bet365,betmgm,caesars,betrivers,fanatics,hardrock"
            ).split(",") if x.strip()]
            max_browser = int(os.getenv("PH_FAST_BROWSER_JOBS", "6"))
            browser_sports = _season_active_sports(sports)
            print(
                f"no verified direct prices — browser fallback: "
                f"{','.join(browser_sports)} / {max_browser} jobs",
                flush=True,
            )
        else:
            books = [x.strip() for x in os.getenv(
                "PH_BROWSER_BOOKS", "bet365,betmgm,caesars,betrivers,superbook,fanatics,hardrock,thescore,betr,dabble,chalkboard,parlayplay"
            ).split(",") if x.strip()]
            max_browser = int(os.getenv("PH_MAX_BROWSER_JOBS", "12"))
            browser_sports = _season_active_sports(sports)

        for source, fn in _browser_jobs(browser_sports, books)[:max_browser]:
            rows, audit = _call(source, fn, max_cache_age)
            all_rows.extend(rows)
            audits.append(audit)
            print(f"source {source}: {len(rows)} | {audit['status']}", flush=True)

    # Final dedup across sources. Source remains part of the key so consensus survives.
    dedup: Dict[str, Dict[str, Any]] = {}
    for row in all_rows:
        dedup[_row_key(row)] = row
    rows = list(dedup.values())
    try:
        from prop_hunter_market_consensus import enrich as _enrich_consensus
        rows = _enrich_consensus(rows)
    except Exception as exc:
        warn(f"market consensus skipped: {exc}")

    safe_json_write(OUT_FILE, rows)
    safe_json_write("prop_hunter_source_health.json", audits)
    _upsert_chunks("prop_hunter_prop_snapshots", rows, conflict="snapshot_id", size=200)
    audit_db = [{
        "source_name": a.get("item_key"), "sport": ",".join((a.get("payload") or {}).get("sports", [])),
        "check_type": "source_health", "status": a.get("status"), "message": a.get("message"),
        "latency_ms": int(float((a.get("payload") or {}).get("elapsed_s", 0)) * 1000),
        "raw": a.get("payload") or {},
    } for a in audits]
    _upsert_chunks("prop_hunter_source_audit", audit_db, conflict=None, size=100)
    persist_registry()
    print(f"ALL FREE SOURCES: {len(rows)} unique rows from {len(audits)} checks", flush=True)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["fast", "all", "browser"], default="fast")
    parser.add_argument("--sport", choices=["MLB", "NBA", "WNBA", "NFL", "NHL"])
    args = parser.parse_args()
    collect(args.sport, args.mode)


if __name__ == "__main__":
    main()
