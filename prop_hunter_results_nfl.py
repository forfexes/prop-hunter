#!/usr/bin/env python3
"""PROP HUNTER — NFL RESULTS

Pending-pick-driven nflverse/nflreadpy weekly stats with schedule mapping so each
player row has the real game_id and game_date required by safe settlement.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from prop_hunter_shared_utils import (
    log, norm_name, safe_json_write, select_settlement_picks as select_pick_rows, to_float, upsert_rows, warn
)

OUT = "prop_hunter_results_nfl_raw.json"

def current_nfl_season(now=None):
    now = now or datetime.now(timezone.utc)
    return now.year if now.month >= 8 else now.year - 1

def _pending(row):
    return str(row.get("status") or row.get("result") or "pending").strip().lower() in {
        "", "pending", "open", "none", "null", "unsettled"
    }

def pending_players(limit=5000):
    seen = {}
    for r in select_pick_rows(limit=limit):
        sport = str(r.get("league") or r.get("sport") or "").upper()
        if sport != "NFL" or not _pending(r):
            continue
        n = str(r.get("player_name") or r.get("player") or "").strip()
        if n:
            seen.setdefault(norm_name(n), n)
    cap = max(1, int(os.getenv("NFL_RESULTS_PLAYER_CAP", "120")))
    return list(seen.values())[:cap]

def _to_pandas(obj):
    try:
        return obj.to_pandas()
    except Exception:
        return obj

def _schedule_map(nfl, seasons):
    out = {}
    try:
        sdf = _to_pandas(nfl.load_schedules(seasons=seasons))
    except Exception as e:
        warn(f"nflreadpy load_schedules failed: {e}")
        return out
    try:
        for _, g in sdf.iterrows():
            season = str(g.get("season") or "")
            week = str(g.get("week") or "")
            away = str(g.get("away_team") or "")
            home = str(g.get("home_team") or "")
            gid = str(g.get("game_id") or g.get("old_game_id") or "")
            gameday = str(g.get("gameday") or g.get("game_date") or "")[:10] or None
            if away:
                out[(season, week, away)] = {"game_id": gid, "game_date": gameday, "opponent": home}
            if home:
                out[(season, week, home)] = {"game_id": gid, "game_date": gameday, "opponent": away}
    except Exception as e:
        warn(f"NFL schedule map parse failed: {e}")
    return out

def nflreadpy_weekly(seasons=None, players=None) -> List[Dict[str, Any]]:
    try:
        import nflreadpy as nfl
    except Exception as e:
        warn(f"nflreadpy unavailable: {e}")
        return []
    seasons = seasons or [int(os.getenv("NFL_SEASON", str(current_nfl_season())))]
    wanted = {norm_name(x) for x in (players or []) if x}
    if not wanted:
        log("NFL results: no pending players -> skip nflverse download")
        return []
    try:
        df = _to_pandas(nfl.load_player_stats(seasons=seasons))
    except Exception as e:
        warn(f"nflreadpy load_player_stats failed: {e}")
        return []
    schedules = _schedule_map(nfl, seasons)
    rows = []
    cap = int(os.getenv("NFL_RESULT_ROW_CAP", "5000"))
    for _, r in df.head(cap).iterrows():
        name = r.get("player_display_name") or r.get("player_name") or r.get("name")
        if not name or norm_name(name) not in wanted:
            continue
        season = str(r.get("season") or seasons[0])
        week = str(r.get("week") or "")
        team = str(r.get("recent_team") or r.get("team") or "")
        meta = schedules.get((season, week, team), {})
        gid = str(meta.get("game_id") or r.get("game_id") or f"{team}_{season}_{week}_{norm_name(name)}")
        game_date = meta.get("game_date") or str(r.get("gameday") or r.get("game_date") or "")[:10] or None
        rush_td = to_float(r.get("rushing_tds"), 0) or 0
        rec_td = to_float(r.get("receiving_tds"), 0) or 0
        pass_td = to_float(r.get("passing_tds"), 0) or 0
        total_td = rush_td + rec_td
        rows.append({
            "sport": "AMERICAN_FOOTBALL", "league": "NFL", "season": season, "week": week,
            "source": "nflreadpy", "source_game_id": gid, "game_id": gid, "game_date": game_date,
            "player_name": name, "normalized_name": norm_name(name), "team": team,
            "opponent": meta.get("opponent") or r.get("opponent_team"),
            "receptions": to_float(r.get("receptions")),
            "receiving_yards": to_float(r.get("receiving_yards")),
            "rushing_yards": to_float(r.get("rushing_yards")),
            "rushing_attempts": to_float(r.get("carries")),
            "passing_yards": to_float(r.get("passing_yards")),
            "passing_touchdowns": pass_td,
            "interceptions": to_float(r.get("interceptions")),
            "receiving_touchdowns": rec_td,
            "rushing_touchdowns": rush_td,
            "touchdowns": total_td,
            "anytime_td": 1.0 if total_td >= 1 else 0.0,
            "two_plus_td": 1.0 if total_td >= 2 else 0.0,
            "three_plus_td": 1.0 if total_td >= 3 else 0.0,
            "targets": to_float(r.get("targets")),
            "raw": dict(r),
        })
    return rows

def main():
    players = pending_players(limit=int(os.getenv("NFL_PICK_SCAN_LIMIT", "5000")))
    seasons = [
        int(x) for x in os.getenv("NFL_RESULT_SEASONS", os.getenv("NFL_SEASON", str(current_nfl_season()))).split(",")
        if x.strip().isdigit()
    ]
    rows = nflreadpy_weekly(seasons, players)
    dated = sum(1 for r in rows if r.get("game_date"))
    safe_json_write(OUT, rows)
    if rows:
        upsert_rows("prop_hunter_player_gamelogs", rows, "sport,league,season,game_id,normalized_name")
    log(f"NFL results done: pending_players={len(players)} rows={len(rows)} dated={dated}")

if __name__ == "__main__":
    main()
