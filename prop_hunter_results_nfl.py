#!/usr/bin/env python3
"""
PROP HUNTER — NFL RESULTS
=========================

Sources:
- nflreadpy / nflverse weekly stats
- ESPN scoreboard backup

Writes:
- prop_hunter_player_gamelogs
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from prop_hunter_shared_utils import http_json, upsert_rows, safe_json_write, log, warn, norm_name, to_float, hash_key

OUT = "prop_hunter_results_nfl_raw.json"

def current_nfl_season(now=None):
    now = now or datetime.now(timezone.utc)
    return now.year if now.month >= 8 else now.year - 1

def nflreadpy_weekly(seasons=None) -> List[Dict[str, Any]]:
    try:
        import nflreadpy as nfl
    except Exception as e:
        warn(f"nflreadpy unavailable: {e}")
        return []

    seasons = seasons or [int(os.getenv("NFL_SEASON", str(current_nfl_season())))]
    try:
        data = nfl.load_player_stats(seasons=seasons)
        try:
            df = data.to_pandas()
        except Exception:
            df = data
    except Exception as e:
        warn(f"nflreadpy load_player_stats failed: {e}")
        return []

    rows = []
    cap = int(os.getenv("NFL_RESULT_ROW_CAP", "5000"))
    for _, r in df.head(cap).iterrows():
        name = r.get("player_display_name") or r.get("player_name") or r.get("name")
        if not name:
            continue
        season = str(r.get("season") or seasons[0])
        week = str(r.get("week") or "")
        game_id = str(r.get("recent_team") or "") + "_" + season + "_" + week + "_" + norm_name(name)
        rush_td = to_float(r.get("rushing_tds"), 0) or 0
        rec_td = to_float(r.get("receiving_tds"), 0) or 0
        pass_td = to_float(r.get("passing_tds"), 0) or 0
        rows.append({
            "sport": "AMERICAN_FOOTBALL",
            "league": "NFL",
            "season": season,
            "week": week,
            "source": "nflreadpy",
            "source_game_id": game_id,
            "game_id": game_id,
            "player_name": name,
            "normalized_name": norm_name(name),
            "team": r.get("recent_team"),
            "opponent": r.get("opponent_team"),
            "receptions": to_float(r.get("receptions")),
            "receiving_yards": to_float(r.get("receiving_yards")),
            "rushing_yards": to_float(r.get("rushing_yards")),
            "rush_attempts": to_float(r.get("carries")),
            "passing_yards": to_float(r.get("passing_yards")),
            "passing_tds": pass_td,
            "interceptions": to_float(r.get("interceptions")),
            "receiving_touchdowns": rec_td,
            "rushing_touchdowns": rush_td,
            "touchdowns": rush_td + rec_td,
            "anytime_td": (rush_td + rec_td) >= 1,
            "two_plus_td": (rush_td + rec_td) >= 2,
            "targets": to_float(r.get("targets")),
            "raw": dict(r),
        })
    return rows

def espn_scoreboard() -> List[Dict[str, Any]]:
    url = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
    data = http_json(url, retries=1) or {}
    rows = []
    for ev in data.get("events", []) or []:
        rows.append({
            "sport": "AMERICAN_FOOTBALL",
            "league": "NFL",
            "source": "espn_scoreboard",
            "game_id": str(ev.get("id")),
            "source_game_id": str(ev.get("id")),
            "game_date": str(ev.get("date") or "")[:10],
            "raw": ev,
        })
    return rows

def main():
    seasons = [int(x) for x in os.getenv("NFL_RESULT_SEASONS", os.getenv("NFL_SEASON", str(current_nfl_season()))).split(",") if x.strip().isdigit()]
    rows = nflreadpy_weekly(seasons)
    rows.extend(espn_scoreboard())
    safe_json_write(OUT, rows)
    upsert_rows("prop_hunter_player_gamelogs", rows, "sport,league,season,game_id,normalized_name")
    log(f"NFL results done: {len(rows)} rows")

if __name__ == "__main__":
    main()
