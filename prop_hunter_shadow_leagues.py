#!/usr/bin/env python3
"""Collect additional leagues in shadow mode.

Shadow rows enrich the data lake but are never card-eligible. They reuse the
existing prop snapshot table and its 7-day retention, so no new table or
unbounded storage path is introduced.
"""
from __future__ import annotations

import os
from collections import Counter
from typing import Any, Dict, List

from prop_hunter_shared_utils import log, now_iso, to_float, upsert_rows
from prop_hunter_source_orchestrator import _normalise, _snapshot_rows_for_db

MAX_EVENTS = max(1, min(5, int(os.getenv("PH_SHADOW_MAX_EVENTS", "3"))))
SHADOW_LEAGUES = {
    "AHL": {"sgo": "icehockey_ahl", "oddspapi": "icehockey_ahl"},
    "SHL": {"sgo": "icehockey_shl", "oddspapi": "icehockey_shl"},
    "NBA_G_LEAGUE": {"sgo": "basketball_g_league", "oddspapi": "basketball_g_league"},
    "CFL": {"sgo": "americanfootball_cfl", "oddspapi": "americanfootball_cfl"},
    "SWISS_NL": {"oddspapi": "icehockey_swiss_nl"},
    "EUROCUP": {"oddspapi": "basketball_eurocup"},
}


def _shadow_row(row: Dict[str, Any], league: str, source_name: str) -> Dict[str, Any] | None:
    row = dict(row or {})
    row["sport"] = league
    row["league"] = league
    row["card_eligible"] = False
    row["settlement_supported"] = False
    row["risk_class"] = "shadow"
    raw = dict(row.get("raw") or {})
    raw.update({
        "shadow_league": True,
        "shadow_source": source_name,
        "card_eligible": False,
        "collected_at": now_iso(),
    })
    row["raw"] = raw
    if not row.get("created_at"):
        row["created_at"] = raw.get("last_updated") or raw.get("changed_at") or now_iso()
    out = _normalise(row, source_name)
    if not out:
        return None
    if not out.get("player_name") or (to_float(out.get("odds_decimal")) or 0) <= 1:
        return None
    return out


def _fetch_sgo(key: str) -> List[Dict[str, Any]]:
    try:
        import prop_hunter_sgo as sgo
        if not sgo.configured():
            return []
        return sgo.fetch_sgo_props(key, max_events=MAX_EVENTS)
    except Exception as exc:
        log(f"shadow SGO {key} failed: {exc}")
        return []


def _fetch_oddspapi(key: str) -> List[Dict[str, Any]]:
    try:
        import prop_hunter_oddspapi as op
        if not op.configured():
            return []
        return op.fetch_oddspapi_props(key, max_events=max(1, min(2, MAX_EVENTS)))
    except Exception as exc:
        log(f"shadow OddsPapi {key} failed: {exc}")
        return []


def main() -> None:
    all_rows: List[Dict[str, Any]] = []
    audit_rows: List[Dict[str, Any]] = []

    for league, providers in SHADOW_LEAGUES.items():
        raw_rows: List[Dict[str, Any]] = []
        used = ""
        if providers.get("sgo"):
            raw_rows = _fetch_sgo(providers["sgo"])
            if raw_rows:
                used = "sportsgameodds"
        if not raw_rows and providers.get("oddspapi"):
            raw_rows = _fetch_oddspapi(providers["oddspapi"])
            if raw_rows:
                used = "oddspapi"

        normalized = []
        for row in raw_rows:
            out = _shadow_row(row, league, used or "shadow")
            if out:
                normalized.append(out)

        dedup = {str(r.get("snapshot_id")): r for r in normalized if r.get("snapshot_id")}
        rows = list(dedup.values())
        all_rows.extend(rows)

        markets = Counter(str(r.get("market_key") or r.get("market") or "") for r in rows)
        books = {str(r.get("bookmaker") or "") for r in rows if r.get("bookmaker")}
        players = {str(r.get("player_name") or "").lower() for r in rows if r.get("player_name")}
        audit_rows.append({
            "source_name": f"shadow_{league.lower()}",
            "sport": league,
            "check_type": "shadow_data",
            "status": "active" if rows else "empty",
            "message": f"provider={used or 'none'} rows={len(rows)} players={len(players)} books={len(books)}",
            "latency_ms": 0,
            "raw": {
                "provider": used or None,
                "rows": len(rows),
                "players": len(players),
                "books": len(books),
                "markets": dict(markets.most_common(25)),
                "card_eligible": False,
                "generated_at": now_iso(),
            },
        })
        log(f"shadow {league}: provider={used or 'none'} rows={len(rows)} players={len(players)} books={len(books)}")

    db_rows = _snapshot_rows_for_db(all_rows)
    for start in range(0, len(db_rows), 200):
        upsert_rows("prop_hunter_prop_snapshots", db_rows[start:start + 200], "snapshot_id")
    if audit_rows:
        upsert_rows("prop_hunter_source_audit", audit_rows, None)
    log(f"shadow data done rows={len(db_rows)} leagues={len(SHADOW_LEAGUES)}")


if __name__ == "__main__":
    main()
