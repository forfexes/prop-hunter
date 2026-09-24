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

try:
    from prop_hunter_identity_hub import identity_match, learn_aliases
except Exception:
    identity_match = lambda a, b, threshold=94, aliases=None: norm_name(a) == norm_name(b)
    learn_aliases = lambda rows: {}

OUT = "prop_hunter_results_settled.json"

MARKET_STAT_MAP = {
    # NBA / WNBA
    "points rebounds assists": "pra", "pra": "pra",
    "points rebounds": "pr", "points assists": "pa",
    "rebounds assists": "ra", "rba": "ra", "ra": "ra",
    "double double": "double_double", "triple double": "triple_double",
    "three pointers": "threes_made", "3 pointers": "threes_made", "3pm": "threes_made",
    "rebounds": "rebounds", "reb": "rebounds",
    "assists": "assists", "ast": "assists",
    "blocks": "blocks", "steals": "steals", "points": "points", "pts": "points",
    # MLB
    "pitcher hits allowed": "pitcher_hits_allowed", "hits allowed": "pitcher_hits_allowed",
    "pitcher earned runs": "pitcher_earned_runs", "earned runs": "pitcher_earned_runs",
    "pitcher outs": "pitcher_outs", "outs recorded": "pitcher_outs",
    "pitcher strikeouts": "pitcher_strikeouts", "pitcher k": "pitcher_strikeouts",
    "stolen bases": "stolen_bases", "stolen base": "stolen_bases",
    "total bases": "total_bases", "home run": "home_runs", "hr": "home_runs",
    "rbi": "rbi", "hits": "hits", "hit": "hits", "runs": "runs",
    # NFL
    "passing touchdowns": "passing_touchdowns", "pass tds": "passing_touchdowns",
    "receiving yards": "receiving_yards", "rushing yards": "rushing_yards",
    "passing yards": "passing_yards", "receptions": "receptions",
    "3 plus td": "three_plus_td", "3plus td": "three_plus_td", "3 td": "three_plus_td",
    "2 plus td": "two_plus_td", "2plus td": "two_plus_td", "2 td": "two_plus_td",
    "anytime td": "anytime_td", "1 plus td": "anytime_td", "1plus td": "anytime_td", "1 td": "anytime_td", "touchdown": "anytime_td",
    # NHL (settles when these columns are present in gamelogs)
    "shots on goal": "shots_on_goal", "goalie saves": "goalie_saves",
    "blocked shots": "blocked_shots", "power play points": "power_play_points",
    "goals": "goals", "nhl assists": "nhl_assists", "nhl points": "nhl_points",
}


def detect_stat(market: Any) -> Optional[str]:
    m = norm_market(market)
    for k in sorted(MARKET_STAT_MAP, key=len, reverse=True):
        if k in m:
            return MARKET_STAT_MAP[k]
    return None


def stat_value(gl: Dict[str, Any], stat: str) -> Any:
    # Direct DB columns first.
    if stat in gl and gl.get(stat) is not None:
        return gl.get(stat)
    if stat == "pra":
        vals = [to_float(gl.get(x)) for x in ("points", "rebounds", "assists")]
        return sum(vals) if all(v is not None for v in vals) else None
    if stat == "pr":
        vals = [to_float(gl.get(x)) for x in ("points", "rebounds")]
        return sum(vals) if all(v is not None for v in vals) else None
    if stat == "pa":
        vals = [to_float(gl.get(x)) for x in ("points", "assists")]
        return sum(vals) if all(v is not None for v in vals) else None
    if stat == "ra":
        vals = [to_float(gl.get(x)) for x in ("rebounds", "assists")]
        return sum(vals) if all(v is not None for v in vals) else None
    if stat in {"double_double", "triple_double"}:
        vals = [to_float(gl.get(x)) for x in ("points", "rebounds", "assists", "blocks", "steals")]
        vals = [v for v in vals if v is not None]
        needed = 2 if stat == "double_double" else 3
        return bool(sum(1 for v in vals if v >= 10) >= needed) if vals else None
    if stat == "pitcher_outs":
        inn = to_float(gl.get("pitcher_innings"))
        if inn is None:
            return None
        whole = int(inn)
        frac = round(inn - whole, 2)
        # Baseball notation 6.1 / 6.2 means one / two outs, not decimal innings.
        extra = 1 if 0.09 <= frac < 0.19 else 2 if 0.19 <= frac < 0.29 else 0
        return whole * 3 + extra
    if stat == "anytime_td":
        vals = [to_float(gl.get(x), 0.0) or 0.0 for x in ("receiving_touchdowns", "rushing_touchdowns")]
        return bool(sum(vals) >= 1)
    if stat == "two_plus_td":
        vals = [to_float(gl.get(x), 0.0) or 0.0 for x in ("receiving_touchdowns", "rushing_touchdowns")]
        return bool(sum(vals) >= 2)
    if stat == "three_plus_td":
        vals = [to_float(gl.get(x), 0.0) or 0.0 for x in ("receiving_touchdowns", "rushing_touchdowns")]
        return bool(sum(vals) >= 3)
    aliases = {
        "passing_touchdowns": ("passing_touchdowns", "passing_tds"),
        "nhl_assists": ("assists", "nhl_assists", "assists_hockey"),
        "nhl_points": ("points", "nhl_points", "hockey_points"),
        "shots_on_goal": ("shots_on_goal", "shots"),
        "goalie_saves": ("goalie_saves", "saves"),
        "blocked_shots": ("blocked_shots", "blocks"),
        "power_play_points": ("power_play_points", "ppp"),
    }
    # Generic Points/Assists market names are shared by basketball and hockey.
    # Use NHL-specific columns when the gamelog tells us this is hockey.
    league = str(gl.get("league") or gl.get("sport") or "").upper()
    if league == "NHL" and stat == "points":
        for key in ("hockey_points", "nhl_points", "points"):
            if gl.get(key) is not None:
                return gl.get(key)
    if league == "NHL" and stat == "assists":
        for key in ("assists_hockey", "nhl_assists", "assists"):
            if gl.get(key) is not None:
                return gl.get(key)
    for key in aliases.get(stat, ()):
        if gl.get(key) is not None:
            return gl.get(key)
    return None

def side_of_pick(pick: Dict[str, Any]) -> str:
    s = str(pick.get("side") or pick.get("direction") or pick.get("over_under") or pick.get("pick_side") or "").lower()
    text = str(pick.get("market") or pick.get("selection") or pick.get("pick") or "").lower()
    if "under" in s or "under" in text:
        return "under"
    return "over"

def line_of_pick(pick: Dict[str, Any]) -> Optional[float]:
    for k in ("line", "point", "prop_line", "points", "threshold"):
        v = to_float(pick.get(k))
        if v is not None:
            return v
    # Newer and legacy pick rows sometimes embed the threshold only in market text.
    # Use the last numeric token: "Points Over 20.5" -> 20.5, "2+ TD" -> 2.
    import re
    text = str(pick.get("market") or pick.get("selection") or pick.get("pick") or "")
    nums = re.findall(r"(?<![A-Za-z])(\d+(?:\.\d+)?)", text)
    return float(nums[-1]) if nums else None

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

def _date_only(value: Any):
    from datetime import date, datetime
    if not value:
        return None
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except Exception:
        try:
            return date.fromisoformat(text[:10])
        except Exception:
            return None


def _pick_target_date(pick: Dict[str, Any]):
    raw = pick.get("raw") if isinstance(pick.get("raw"), dict) else {}
    for value in (
        pick.get("commence_time"), raw.get("commence_time"),
        pick.get("game_date"), pick.get("sent_date"), pick.get("date"), pick.get("created_at"),
    ):
        d = _date_only(value)
        if d is not None:
            return d
    return None


def find_gamelog(pick: Dict[str, Any], logs: List[Dict[str, Any]], aliases=None) -> Optional[Dict[str, Any]]:
    """Find the intended game without ever settling against an arbitrary old log.

    Provider event ids usually differ (sportsbook id vs official league id), so after
    exact id matching we use player identity + a narrow date window. If two logs are
    equally plausible (e.g. an MLB doubleheader), we leave the pick pending instead
    of grading the wrong game.
    """
    pname = pick.get("player_name") or pick.get("player") or pick.get("selection")
    game_id = str(pick.get("game_id") or pick.get("source_game_id") or "")
    player_logs = [
        gl for gl in logs
        if (not pname or identity_match(pname, gl.get("player_name"), threshold=94, aliases=aliases))
    ]
    if not player_logs:
        return None

    if game_id:
        exact = [
            gl for gl in player_logs
            if str(gl.get("game_id") or gl.get("source_game_id") or "") == game_id
        ]
        if len(exact) == 1:
            return exact[0]
        if len(exact) > 1:
            return None

    target = _pick_target_date(pick)
    if target is None:
        # No date context: refusing to guess is safer than grading from a random
        # historical game for that player.
        return None

    dated = []
    for gl in player_logs:
        gd = _date_only(gl.get("game_date") or gl.get("date"))
        if gd is None:
            continue
        delta = (gd - target).days
        # UTC sportsbook timestamps can be one calendar day ahead of US local dates.
        if -1 <= delta <= 2:
            dated.append((abs(delta), 0 if delta == 0 else 1 if delta == -1 else 2 + delta, gl))
    if not dated:
        return None
    dated.sort(key=lambda x: (x[0], x[1]))
    best_rank = dated[0][:2]
    best = [gl for dist, pref, gl in dated if (dist, pref) == best_rank]
    return best[0] if len(best) == 1 else None

def load_picks():
    return select_pick_rows(limit=int(os.getenv("SETTLE_PICK_LIMIT", "5000")))

def main():
    picks = load_picks()
    logs = select_rows("prop_hunter_player_gamelogs", limit=int(os.getenv("SETTLE_LOG_LIMIT", "20000")))
    settled = []
    aliases = learn_aliases(list(picks) + list(logs))
    for p in picks:
        stat = detect_stat(p.get("market") or p.get("prop_type") or p.get("selection"))
        if not stat:
            continue
        gl = find_gamelog(p, logs, aliases=aliases)
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
