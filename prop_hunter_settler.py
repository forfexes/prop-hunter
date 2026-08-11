#!/usr/bin/env python3
"""
PROP HUNTER — SETTLER
=====================

Setzt Picks gegen gespeicherte Player-Gamelogs ab.

Input:
- prop_hunter_picks oder prop_picks
- prop_hunter_player_gamelogs

Output:
- prop_hunter_results
- prop_hunter_results_settled.json

Unterstützte Märkte:
NBA/WNBA: points, rebounds, assists, pra, ra/rba, double_double, triple_double
MLB: hits, total_bases, home_runs, rbi, runs, pitcher_strikeouts
NFL: receiving_yards, rushing_yards, passing_yards, anytime_td, 2plus_td, receptions
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple, List

from prop_hunter_shared_utils import (
    select_rows, select_pick_rows, upsert_rows, safe_json_write, log, warn, norm_name, norm_market,
    to_float, hash_key, now_iso, pick_id
)

OUT = "prop_hunter_results_settled.json"

MARKET_STAT_MAP = {
    "points": "points",
    "pts": "points",
    "rebounds": "rebounds",
    "reb": "rebounds",
    "assists": "assists",
    "ast": "assists",
    "pra": "pra",
    "points rebounds assists": "pra",
    "ra": "ra",
    "rba": "ra",
    "rebounds assists": "ra",
    "double double": "double_double",
    "triple double": "triple_double",
    "hits": "hits",
    "hit": "hits",
    "total bases": "total_bases",
    "home run": "home_runs",
    "hr": "home_runs",
    "rbi": "rbi",
    "runs": "runs",
    "strikeouts": "pitcher_strikeouts",
    "pitcher strikeouts": "pitcher_strikeouts",
    "pitcher k": "pitcher_strikeouts",
    "receiving yards": "receiving_yards",
    "rushing yards": "rushing_yards",
    "passing yards": "passing_yards",
    "receptions": "receptions",
    "anytime td": "anytime_td",
    "touchdown": "anytime_td",
    "2plus td": "two_plus_td",
    "2 td": "two_plus_td",
}

def detect_stat(market: Any) -> Optional[str]:
    m = norm_market(market)
    for k, v in MARKET_STAT_MAP.items():
        if k in m:
            return v
    return None

def side_of_pick(pick: Dict[str, Any]) -> str:
    s = str(pick.get("side") or pick.get("direction") or pick.get("over_under") or pick.get("pick_side") or "").lower()
    text = str(pick.get("market") or pick.get("selection") or pick.get("pick") or "").lower()
    if "under" in s or "under" in text:
        return "under"
    return "over"

def line_of_pick(pick: Dict[str, Any]) -> Optional[float]:
    for k in ("line", "prop_line", "points", "threshold"):
        v = to_float(pick.get(k))
        if v is not None:
            return v
    return None

def result_for_value(value: Any, line: Optional[float], side: str) -> str:
    if value is None:
        return "no_result"
    if isinstance(value, bool):
        return "win" if value else "loss"
    v = to_float(value)
    if v is None or line is None:
        return "no_result"
    if v == line:
        return "push"
    if side == "under":
        return "win" if v < line else "loss"
    return "win" if v > line else "loss"

def find_gamelog(pick: Dict[str, Any], logs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    pname = norm_name(pick.get("player_name") or pick.get("player") or pick.get("selection"))
    sport = str(pick.get("sport") or "").upper()
    league = str(pick.get("league") or "").upper()
    game_id = str(pick.get("game_id") or pick.get("source_game_id") or "")
    for gl in logs:
        if pname and norm_name(gl.get("player_name")) != pname:
            continue
        if game_id and str(gl.get("game_id") or gl.get("source_game_id")) != game_id:
            continue
        return gl
    for gl in logs:
        if pname and norm_name(gl.get("player_name")) == pname:
            return gl
    return None

def load_picks():
    return select_pick_rows(limit=int(os.getenv("SETTLE_PICK_LIMIT", "5000")))

def main():
    picks = load_picks()
    logs = select_rows("prop_hunter_player_gamelogs", limit=int(os.getenv("SETTLE_LOG_LIMIT", "20000")))
    settled = []
    for p in picks:
        stat = detect_stat(p.get("market") or p.get("prop_type") or p.get("selection"))
        if not stat:
            continue
        gl = find_gamelog(p, logs)
        if not gl:
            continue
        value = gl.get(stat)
        side = side_of_pick(p)
        line = line_of_pick(p)
        status = result_for_value(value, line, side)
        pid = pick_id(p)
        settled.append({
            "result_id": hash_key(pid, stat, gl.get("game_id")),
            "pick_id": pid,
            "sport": p.get("sport") or gl.get("sport"),
            "league": p.get("league") or gl.get("league"),
            "player_name": p.get("player_name") or p.get("player") or gl.get("player_name"),
            "normalized_name": norm_name(p.get("player_name") or p.get("player") or gl.get("player_name")),
            "market": p.get("market") or p.get("prop_type") or p.get("selection"),
            "stat_key": stat,
            "line": line,
            "side": side,
            "actual_value": value,
            "result": status,
            "game_id": gl.get("game_id"),
            "settled_at": now_iso(),
            "pick_raw": p,
            "result_raw": gl,
        })
    safe_json_write(OUT, settled)
    upsert_rows("prop_hunter_results", settled, "result_id")
    log(f"settler done: picks={len(picks)} logs={len(logs)} settled={len(settled)}")

if __name__ == "__main__":
    main()
