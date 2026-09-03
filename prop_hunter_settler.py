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
NBA/WNBA: points, rebounds, assists, pra, ra/rba, pa, pr, threes_made, double_double, triple_double
MLB: hits, total_bases, home_runs, rbi, runs, pitcher_strikeouts, stolen_bases, hits_runs_rbis
NFL: receiving_yards, rushing_yards, passing_yards, anytime_td, 2plus_td, receptions
NHL: shots_on_goal, goals, hockey_points, assists_hockey, goalie_saves, blocked_shots
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
    "pa": "pa",
    "points assists": "pa",
    "pr": "pr",
    "points rebounds": "pr",
    "3 pt made": "threes_made",
    "3pm": "threes_made",
    "threes made": "threes_made",
    "three pointers made": "threes_made",
    "ra": "ra",
    "rba": "ra",
    "rebounds assists": "ra",
    "double double": "double_double",
    "triple double": "triple_double",
    "hits runs rbis": "hits_runs_rbis",
    "hits runs rbi": "hits_runs_rbis",
    "hits": "hits",
    "hit": "hits",
    "total bases": "total_bases",
    "home run": "home_runs",
    "hr": "home_runs",
    "stolen base": "stolen_bases",
    "rbi": "rbi",
    "runs": "runs",
    "strikeouts": "pitcher_strikeouts",
    "pitcher strikeouts": "pitcher_strikeouts",
    "pitcher k": "pitcher_strikeouts",
    "receiving yards": "receiving_yards",
    "rushing yards": "rushing_yards",
    "passing yards": "passing_yards",
    "receptions": "receptions",
    "receiving touchdowns": "receiving_touchdowns",
    "receiving tds": "receiving_touchdowns",
    "anytime td": "anytime_td",
    "touchdown": "anytime_td",
    "2plus td": "two_plus_td",
    "2 td": "two_plus_td",
    "shots on goal": "shots_on_goal",
    "sog": "shots_on_goal",
    "player shots": "shots_on_goal",
    "hockey points": "hockey_points",
    "player points": "hockey_points",
    "goals": "goals",
    "goal scorer": "goals",
    "assists hockey": "assists_hockey",
    "player assists": "assists_hockey",
    "goalie saves": "goalie_saves",
    "saves": "goalie_saves",
    "blocked shots": "blocked_shots",
    "power play points": "power_play_points",
}

def detect_stat(market: Any) -> Optional[str]:
    m = norm_market(market)
    for k, v in MARKET_STAT_MAP.items():
        if k in m:
            return v
    return None

def side_of_pick(pick: Dict[str, Any]) -> str:
    s = str(pick.get("settlement_direction") or pick.get("side") or pick.get("direction") or pick.get("over_under") or pick.get("pick_side") or "").lower()
    text = str(pick.get("market") or pick.get("selection") or pick.get("pick") or "").lower()
    if "under" in s or "under" in text:
        return "under"
    return "over"

def line_of_pick(pick: Dict[str, Any]) -> Optional[float]:
    for k in ("settlement_line", "line", "prop_line", "points", "threshold"):
        v = to_float(pick.get(k))
        if v is not None:
            return v
    return None


def stat_value(gl: Dict[str, Any], stat: str) -> Any:
    """Return a stored or safely derived settlement value."""
    if stat == "pa":
        a, b = to_float(gl.get("points")), to_float(gl.get("assists"))
        return None if a is None or b is None else a + b
    if stat == "pr":
        a, b = to_float(gl.get("points")), to_float(gl.get("rebounds"))
        return None if a is None or b is None else a + b
    if stat == "hits_runs_rbis":
        vals = [to_float(gl.get(k)) for k in ("hits", "runs", "rbi")]
        return None if any(v is None for v in vals) else sum(vals)
    if stat == "threes_made":
        return gl.get("threes_made") if gl.get("threes_made") is not None else gl.get("three_pointers_made")
    return gl.get(stat)

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
    """Match a pick to its own game only.

    Never settle a historical pick against an arbitrary/latest player game.  Prefer
    explicit game_id; otherwise require the pick date to equal the gamelog date.
    """
    pname = norm_name(pick.get("player_name") or pick.get("player") or pick.get("selection"))
    sport = str(pick.get("sport") or "").upper()
    league = str(pick.get("league") or "").upper()
    game_id = str(pick.get("game_id") or pick.get("source_game_id") or pick.get("match_id") or "")
    pick_date = str(pick.get("game_date") or pick.get("date") or pick.get("sent_date") or "")[:10]

    candidates = []
    for gl in logs:
        if pname and norm_name(gl.get("player_name")) != pname:
            continue
        gl_sport = str(gl.get("sport") or "").upper()
        gl_league = str(gl.get("league") or "").upper()
        if sport and gl_sport and sport not in (gl_sport, gl_league) and league not in (gl_sport, gl_league):
            # Accept aliases such as MLB vs BASEBALL and WNBA vs BASKETBALL through league below.
            aliases = {"MLB": {"MLB", "BASEBALL"}, "BASEBALL": {"MLB", "BASEBALL"},
                       "NBA": {"NBA", "BASKETBALL"}, "WNBA": {"WNBA", "BASKETBALL"},
                       "NFL": {"NFL", "AMERICAN_FOOTBALL"}, "AMERICAN_FOOTBALL": {"NFL", "AMERICAN_FOOTBALL"},
                       "NHL": {"NHL", "HOCKEY", "ICE_HOCKEY"}, "HOCKEY": {"NHL", "HOCKEY", "ICE_HOCKEY"}}
            allowed = aliases.get(sport, {sport})
            if gl_sport not in allowed and gl_league not in allowed:
                continue
        candidates.append(gl)

    if game_id:
        for gl in candidates:
            if str(gl.get("game_id") or gl.get("source_game_id") or "") == game_id:
                return gl
        return None

    if pick_date:
        dated = [gl for gl in candidates if str(gl.get("game_date") or gl.get("date") or "")[:10] == pick_date]
        if len(dated) == 1:
            return dated[0]
        # Multiple same-day rows are only safe if they all resolve to the same game id.
        ids = {str(gl.get("game_id") or gl.get("source_game_id") or "") for gl in dated}
        if len(dated) > 1 and len(ids - {""}) == 1:
            return dated[0]
        return None

    # No game id and no date = insufficient evidence for settlement.
    return None

def load_picks():
    return select_pick_rows(limit=int(os.getenv("SETTLE_PICK_LIMIT", "5000")))

def main():
    picks = load_picks()
    logs = select_rows("prop_hunter_player_gamelogs", limit=int(os.getenv("SETTLE_LOG_LIMIT", "20000")))
    settled = []
    for p in picks:
        stat = detect_stat(p.get("settlement_market") or p.get("market") or p.get("prop_type") or p.get("selection"))
        league = str(p.get("league") or p.get("sport") or "").upper()
        if league == "NHL":
            if stat == "points": stat = "hockey_points"
            elif stat == "assists": stat = "assists_hockey"
        if not stat:
            continue
        gl = find_gamelog(p, logs)
        if not gl:
            continue
        value = stat_value(gl, stat)
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
