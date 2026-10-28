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
NBA/WNBA/NCAAB: points, rebounds, assists, pra, ra/rba, threes, double_double, triple_double
MLB: hits, doubles, triples, total_bases, home_runs, rbi, runs, stolen_bases, pitcher props
NFL/NCAAF: receiving_yards, rushing_yards, passing_yards, passing_touchdowns, anytime/2+/3+ TD, receptions
NHL: goals, assists, points, shots_on_goal, goalie_saves, blocked_shots, power_play_points
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, Tuple, List

from prop_hunter_shared_utils import (
    select_rows, select_pick_rows, upsert_rows, safe_json_write, log, warn, norm_name, norm_market,
    to_float, hash_key, now_iso, pick_id, supabase_client
)

try:
    from prop_hunter_identity_hub import identity_match, learn_aliases
except Exception:
    identity_match = lambda a, b, threshold=94, aliases=None: norm_name(a) == norm_name(b)
    learn_aliases = lambda rows: {}

OUT = "prop_hunter_results_settled.json"

MARKET_STAT_MAP = {
    # NBA / WNBA / NCAAB
    "points rebounds assists": "pra", "pra": "pra",
    "points rebounds": "pr", "points assists": "pa",
    "rebounds assists": "ra", "rba": "ra", "ra": "ra",
    "double double": "double_double", "triple double": "triple_double",
    "three pointers": "threes_made", "3 pointers": "threes_made", "3pm": "threes_made", "threes": "threes_made",
    "rebounds": "rebounds", "reb": "rebounds",
    "assists": "assists", "ast": "assists",
    "blocks": "blocks", "steals": "steals", "points": "points", "pts": "points",
    # MLB — order-specific keys are sorted longest-first in detect_stat
    "pitcher hits allowed": "pitcher_hits_allowed", "hits allowed": "pitcher_hits_allowed",
    "pitcher earned runs": "pitcher_earned_runs", "earned runs": "pitcher_earned_runs",
    "pitcher outs": "pitcher_outs", "outs recorded": "pitcher_outs",
    "pitcher strikeouts": "pitcher_strikeouts", "pitcher k": "pitcher_strikeouts",
    "stolen bases": "stolen_bases", "stolen base": "stolen_bases",
    "total bases": "total_bases", "home runs": "home_runs", "home run": "home_runs", "hr": "home_runs",
    "triples": "triples", "triple": "triples", "doubles": "doubles", "double": "doubles",
    "singles": "singles", "single": "singles",
    "rbi": "rbi", "hits": "hits", "hit": "hits", "runs": "runs",
    # NFL / NCAAF
    "passing touchdowns": "passing_touchdowns", "pass tds": "passing_touchdowns", "pass td": "passing_touchdowns",
    "receiving yards": "receiving_yards", "rushing yards": "rushing_yards",
    "rushing attempts": "rushing_attempts", "rush attempts": "rushing_attempts",
    "carries": "rushing_attempts",
    "passing yards": "passing_yards", "receptions": "receptions",
    "tackles": "tackles", "defensive tackles": "tackles",
    "field goals made": "field_goals_made", "successful field goals": "field_goals_made",
    "kicking points": "kicking_points",
    "3 plus td": "three_plus_td", "3plus td": "three_plus_td", "3 td": "three_plus_td",
    "2 plus td": "two_plus_td", "2plus td": "two_plus_td", "2 td": "two_plus_td",
    "anytime td": "anytime_td", "1 plus td": "anytime_td", "1plus td": "anytime_td", "1 td": "anytime_td", "touchdown": "anytime_td",
    # NHL
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
    if stat in gl and gl.get(stat) is not None:
        return gl.get(stat)
    if stat == "singles":
        parts = [to_float(gl.get(x)) for x in ("hits", "doubles", "triples", "home_runs")]
        if any(v is None for v in parts):
            return None
        return max(0.0, parts[0] - parts[1] - parts[2] - parts[3])
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
    market = str(pick.get("market") or pick.get("prop_type") or pick.get("selection") or pick.get("pick") or "")
    market_norm = re.sub(r"[^a-z0-9]+", " ", market.lower()).strip()
    binary = (
        "home run" in market_norm or re.search(r"\bhr\b", market_norm) or
        "anytime td" in market_norm or "anytime touchdown" in market_norm or
        "double double" in market_norm or "triple double" in market_norm
    )
    for k in ("line", "point", "prop_line", "points", "threshold"):
        v = to_float(pick.get(k))
        if v is not None:
            # Guard legacy parser corruption such as Home Run Over 0.5 -> 5000.
            if binary and (v < 0 or v > 10):
                continue
            return v
    nums = re.findall(r"(?<![A-Za-z])(\d+(?:\.\d+)?)", market)
    if nums:
        v = float(nums[-1])
        if not binary or v <= 10:
            return v
    # Yes/no and scorer-style props are 0.5 thresholds when no explicit line exists.
    if binary:
        return 0.5
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


def _pick_commence_dt(pick: Dict[str, Any]):
    raw = pick.get("raw") if isinstance(pick.get("raw"), dict) else {}
    value = pick.get("commence_time") or raw.get("commence_time")
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _pick_ready_for_settlement(pick: Dict[str, Any]) -> bool:
    """Never grade a pick against an older gamelog before its event could be final."""
    start = _pick_commence_dt(pick)
    if start is None:
        return True
    sport = str(pick.get("sport") or pick.get("league") or "").upper()
    hours = {
        "MLB": 4.0,
        "BASEBALL": 4.0,
        "NFL": 5.0,
        "NCAAF": 5.0,
        "NBA": 3.5,
        "WNBA": 3.5,
        "NCAAB": 3.5,
        "EUROLEAGUE": 3.5,
        "NHL": 4.0,
    }.get(sport, 4.0)
    return datetime.now(timezone.utc) >= start + timedelta(hours=hours)


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


def build_log_index(logs: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Index gamelogs by canonical player name for fast settlement lookups."""
    out: Dict[str, List[Dict[str, Any]]] = {}
    for gl in logs:
        nk = str(gl.get("normalized_name") or "").strip() or norm_name(gl.get("player_name"))
        if nk:
            out.setdefault(nk, []).append(gl)
    return out


def find_gamelog(
    pick: Dict[str, Any],
    logs: List[Dict[str, Any]],
    aliases=None,
    log_index: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> Optional[Dict[str, Any]]:
    pname = pick.get("player_name") or pick.get("player") or pick.get("selection")
    game_id = str(pick.get("game_id") or pick.get("source_game_id") or "")
    player_logs: List[Dict[str, Any]] = []
    if pname and log_index is not None:
        player_logs = list(log_index.get(norm_name(pname), []))
    if not player_logs:
        player_logs = [
            gl for gl in logs
            if (not pname or identity_match(pname, gl.get("player_name"), threshold=94, aliases=aliases))
        ]
    if not player_logs:
        return None

    if not _pick_ready_for_settlement(pick):
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
        return None

    dated = []
    for gl in player_logs:
        gd = _date_only(gl.get("game_date") or gl.get("date"))
        if gd is None:
            continue
        delta = (gd - target).days
        start_dt = _pick_commence_dt(pick)
        # For North-American late-night events, a UTC start shortly after midnight
        # can legitimately have an official local game_date one day earlier.
        allow_previous_day = bool(start_dt and start_dt.hour < 7)
        # NFL sportsbook feeds can label Thursday/Sunday night games by UTC date
        # while nflverse uses the local US gameday.  Accept the immediately
        # previous official gameday for NFL as well, but never a later gamelog.
        league = str(pick.get("league") or pick.get("sport") or "").upper()
        allow_previous_day = allow_previous_day or league in {"NFL", "AMERICAN_FOOTBALL"}
        # Settlement may match the official event date, or the previous local
        # calendar date. Never match a later gamelog (+1/+2 days): that can
        # grade a future card against a different game by the same player.
        if delta == 0 or (delta == -1 and allow_previous_day):
            dated.append((abs(delta), 0 if delta == 0 else 1, gl))
    if not dated:
        return None
    dated.sort(key=lambda x: (x[0], x[1]))
    best_rank = dated[0][:2]
    best = [gl for dist, pref, gl in dated if (dist, pref) == best_rank]
    return best[0] if len(best) == 1 else None

def _load_relevant_gamelogs(picks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Load only current gamelogs for players that actually have pending picks.

    The old global newest-N query became unsafe once backfills pushed the table
    above 100k rows: recent WNBA/NHL rows could sit outside the newest 20k ids
    and remain pending forever.  Filter by normalized player names + game date
    instead, then page deterministically.
    """
    sb = supabase_client()
    if sb is None:
        return select_rows(
            "prop_hunter_player_gamelogs",
            limit=int(os.getenv("SETTLE_LOG_LIMIT", "20000")),
            order_by="id",
            desc=True,
        )

    names = sorted({
        norm_name(p.get("player_name") or p.get("player") or p.get("selection"))
        for p in (picks or [])
        if norm_name(p.get("player_name") or p.get("player") or p.get("selection"))
    })
    if not names:
        return []

    dates = [d for d in (_pick_target_date(p) for p in (picks or [])) if d is not None]
    today = datetime.now(timezone.utc).date()
    lookback = max(3, int(os.getenv("PH_SETTLE_LOOKBACK_DAYS", "14")))
    floor = today - timedelta(days=lookback)
    # Pending debt can be months old (legacy WNBA/MLB).  Do not clamp the
    # targeted read to the recent lookback window: collectors may have just
    # backfilled exactly those historical player/date rows.  The query is
    # already bounded by pending player names, so widening to the oldest
    # pending date remains deterministic and avoids scanning unrelated players.
    oldest_pending = min(dates) if dates else floor
    newest_pending = max(dates) if dates else today
    start = oldest_pending - timedelta(days=1)
    end = min(newest_pending, today + timedelta(days=2)) + timedelta(days=2)

    rows: List[Dict[str, Any]] = []
    batch_size = max(20, min(100, int(os.getenv("PH_SETTLE_PLAYER_BATCH", "80"))))
    page_size = 1000
    try:
        for offset in range(0, len(names), batch_size):
            batch = names[offset:offset + batch_size]
            start_row = 0
            while True:
                q = (
                    sb.table("prop_hunter_player_gamelogs")
                    .select("*")
                    .in_("normalized_name", batch)
                    .gte("game_date", start.isoformat())
                    .lte("game_date", end.isoformat())
                    .order("id", desc=True)
                )
                res = q.range(start_row, start_row + page_size - 1).execute()
                chunk = list(res.data or [])
                rows.extend(chunk)
                if len(chunk) < page_size:
                    break
                start_row += page_size
        log(
            f"settler gamelogs targeted: players={len(names)} "
            f"window={start.isoformat()}..{end.isoformat()} rows={len(rows)}"
        )
        return rows
    except Exception as exc:
        warn(f"targeted settler gamelog read failed, using bounded fallback: {exc}")
        return select_rows(
            "prop_hunter_player_gamelogs",
            limit=int(os.getenv("SETTLE_LOG_LIMIT", "20000")),
            order_by="id",
            desc=True,
        )


def load_picks():
    return select_pick_rows(limit=int(os.getenv("SETTLE_PICK_LIMIT", "5000")))

def main():
    picks = load_picks()
    pending_status = {"", "pending", "open", "none", "null", "unsettled"}
    picks = [
        p for p in picks
        if str(p.get("status") or p.get("result") or "pending").lower() in pending_status
    ]
    logs = _load_relevant_gamelogs(picks)
    settled = []
    aliases = learn_aliases(list(picks) + list(logs))
    log_index = build_log_index(logs)
    for p in picks:
        stat = detect_stat(p.get("market") or p.get("prop_type") or p.get("selection"))
        if not stat:
            continue
        gl = find_gamelog(p, logs, aliases=aliases, log_index=log_index)
        if not gl:
            continue
        value = stat_value(gl, stat)
        side = side_of_pick(p)
        line = line_of_pick(p)
        status = result_for_value(value, line, side)
        pid = pick_id(p)
        settled.append({
            "result_id": hash_key("pick", pid),
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
