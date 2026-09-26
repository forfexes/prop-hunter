#!/usr/bin/env python3
"""MLB doubles/triples result supplement for PROP HUNTER.

Only fetches hitters with pending doubles/triples props. This keeps the normal
MLB collector unchanged while closing settlement for newly discovered markets.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

from prop_hunter_results_mlb import (
    current_season, fetch_gamelog, find_player, base_row, merge_rows
)
from prop_hunter_shared_utils import (
    log, norm_name, safe_json_write, select_pick_rows, to_float, upsert_rows, warn
)

OUT = "prop_hunter_results_mlb_extras_raw.json"

def _pending(row: Dict[str, Any]) -> bool:
    return str(row.get("status") or row.get("result") or "pending").strip().lower() in {
        "", "pending", "open", "none", "null", "unsettled"
    }

def _is_mlb(row: Dict[str, Any]) -> bool:
    s = str(row.get("league") or row.get("sport") or "").upper()
    return "MLB" in s or s == "BASEBALL"

def _is_extra_market(row: Dict[str, Any]) -> bool:
    m = str(row.get("market") or row.get("prop_type") or row.get("selection") or "").lower()
    return "double" in m or "triple" in m

def pending_players(limit: int = 5000) -> List[str]:
    seen = {}
    for row in select_pick_rows(limit=limit):
        if not (_pending(row) and _is_mlb(row) and _is_extra_market(row)):
            continue
        name = str(row.get("player_name") or row.get("player") or "").strip()
        if name:
            seen.setdefault(norm_name(name), name)
    cap = max(1, int(os.getenv("PH_MLB_EXTRA_RESULTS_MAX_PLAYERS", "40")))
    return list(seen.values())[:cap]

def parse_extra_hitting(name: str, split: Dict[str, Any], season: str) -> Dict[str, Any]:
    stat = split.get("stat") or {}
    row = base_row(name, split, season)
    row.update({
        "hits": to_float(stat.get("hits")),
        "doubles": to_float(stat.get("doubles")),
        "triples": to_float(stat.get("triples")),
        "total_bases": to_float(stat.get("totalBases")),
        "home_runs": to_float(stat.get("homeRuns")),
        "raw": {"group": "hitting_extra", "split": split},
    })
    return row

def main() -> None:
    season = current_season()
    last_n = max(1, int(os.getenv("LAST_N_GAMES", "30")))
    players = pending_players()
    rows = []
    for player in players:
        try:
            person = find_player(player)
            if not person or not person.get("id"):
                warn(f"MLB extra player not resolved: {player}")
                continue
            canonical = person.get("fullName") or player
            splits = fetch_gamelog(person["id"], "hitting", season)
            splits = sorted(splits, key=lambda x: str(x.get("date") or ""), reverse=True)[:last_n]
            rows.extend(parse_extra_hitting(canonical, split, season) for split in splits)
        except Exception as exc:
            warn(f"MLB extras failed {player}: {exc}")

    rows = merge_rows(rows)
    safe_json_write(OUT, rows)
    if rows:
        upsert_rows(
            "prop_hunter_player_gamelogs", rows,
            "sport,league,season,game_id,normalized_name"
        )
    log(f"MLB extras results done: pending_players={len(players)} rows={len(rows)}")

if __name__ == "__main__":
    main()
