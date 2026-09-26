#!/usr/bin/env python3
"""PROP HUNTER V13.9.2 source orchestrator core.

Keyless/free sources run first. Keyed sources are bounded and only used as needed.
"""
from __future__ import annotations
import argparse, json, os, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from prop_hunter_shared_utils import (
    hash_key, log, now_iso, safe_json_load, safe_json_write, to_float, upsert_rows, warn
)
from prop_hunter_source_catalog import as_rows

OUT_FILE = "prop_hunter_odds_snapshot.json"
HEALTH_FILE = "prop_hunter_source_health.json"
SPORTS = [x.strip().upper() for x in os.getenv("PROP_HUNTER_SPORTS", "MLB,NBA,WNBA,NFL,NHL,NCAAB,NCAAF").split(",") if x.strip()]


def _normalise(row: Dict[str, Any], source: str) -> Optional[Dict[str, Any]]:
    if not isinstance(row, dict):
        return None
    r = dict(row)
    r.setdefault("source", source)
    r.setdefault("bookmaker", r.get("book") or source)
    r.setdefault("sport", r.get("league") or "")
    r.setdefault("league", r.get("sport") or "")
    r.setdefault("source_event_id", r.get("event_id") or r.get("game_id") or "")
    r.setdefault("event_id", r.get("source_event_id") or r.get("game_id") or "")
    r.setdefault("player_name", r.get("player") or r.get("selection") or "")
    r.setdefault("market", r.get("market_key") or r.get("prop_type") or "")
    r.setdefault("market_key", r.get("market") or r.get("prop_type") or "")
    r.setdefault("direction", r.get("side") or "")
    line = to_float(r.get("line") if r.get("line") is not None else r.get("point"))
    if line is not None:
        r["line"] = line
    odds = to_float(r.get("odds_decimal") if r.get("odds_decimal") is not None else r.get("odds"))
    if odds is not None:
        r["odds_decimal"] = odds
    r.setdefault("created_at", now_iso())
    r["snapshot_id"] = str(r.get("snapshot_id") or hash_key(
        r.get("source"), r.get("bookmaker"), r.get("sport"), r.get("source_event_id"),
        r.get("player_name"), r.get("market_key"), r.get("direction"), r.get("line"), r.get("odds_decimal")
    ))
    return r


def _audit(source: str, status: str, rows: List[Dict[str, Any]], elapsed: float, message: str = "") -> Dict[str, Any]:
    sports = sorted({str(r.get("sport") or r.get("league") or "").upper() for r in rows if isinstance(r, dict)})
    books = sorted({str(r.get("bookmaker") or r.get("source") or "").lower() for r in rows if isinstance(r, dict)})
    return {
        "audit_id": hash_key(source, now_iso()[:13]), "section": "source_health", "item_key": source,
        "status": status, "message": message,
        "payload": {"rows": len(rows), "sports": sports, "books": books, "elapsed_s": round(elapsed, 3)},
        "updated_at": now_iso(),
    }


def _call(source: str, fn: Callable[[], Any], max_cache_age_min: int = 8) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    started = time.monotonic()
    try:
        raw = fn() or []
        if isinstance(raw, dict):
            raw = raw.get("rows") or raw.get("data") or []
        rows = []
        for x in raw if isinstance(raw, list) else []:
            n = _normalise(x, source)
            if n is not None:
                rows.append(n)
        status = "ok" if rows else "empty"
        return rows, _audit(source, status, rows, time.monotonic() - started)
    except Exception as exc:
        return [], _audit(source, "error", [], time.monotonic() - started, str(exc)[:400])


def _browser_jobs(sports: Iterable[str], books: Iterable[str]) -> List[Tuple[str, Callable[[], List[Dict[str, Any]]]]]:
    try:
        from prop_hunter_browser_bookies import fetch_browser_source
    except Exception as exc:
        warn(f"browser source module unavailable; browser jobs skipped: {exc}")
        return []
    jobs: List[Tuple[str, Callable[[], List[Dict[str, Any]]]]] = []
    for book in books:
        for sport in sports:
            jobs.append((f"browser_{book}_{sport.lower()}", lambda b=book, s=sport: fetch_browser_source(b, s)[0]))
    return jobs


def _season_active_sports(sports: Iterable[str]) -> List[str]:
    """Keep normal runs lean while including preseason/early posted props."""
    month = datetime.now(timezone.utc).month
    active = []
    for sport in sports:
        if sport == "MLB" and 3 <= month <= 11:
            active.append(sport)
        elif sport == "WNBA" and 5 <= month <= 10:
            active.append(sport)
        elif sport == "NFL" and (month >= 8 or month <= 2):
            active.append(sport)
        elif sport == "NBA" and (month >= 9 or month <= 6):
            active.append(sport)
        elif sport == "NHL" and (month >= 9 or month <= 6):
            active.append(sport)
        elif sport == "NCAAB" and (month >= 10 or month <= 4):
            active.append(sport)
        elif sport == "NCAAF" and (month >= 8 or month <= 1):
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


def _snapshot_rows_for_db(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    transient = {
        "higher_odds_decimal", "lower_odds_decimal",
        "higher_american", "lower_american",
        "higher_payout_multiplier", "lower_payout_multiplier",
        "game_title", "position", "source_payload_observed",
    }
    return [{k: v for k, v in row.items() if k not in transient} for row in (rows or [])]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["fast", "all", "browser"], default="fast")
    ap.add_argument("--sport", default=None)
    args = ap.parse_args()
    # Compatibility entrypoint: the 13.10 wrapper overrides collect/_direct_jobs.
    return collect(sport_filter=args.sport, mode=args.mode)


if __name__ == "__main__":
    main()
