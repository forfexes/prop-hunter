#!/usr/bin/env python3
"""
PROP HUNTER — MLB RESULTS
=========================

Sources:
- MLB StatsAPI schedule + boxscore
- Works for batting and pitching settlement

Writes:
- prop_hunter_player_gamelogs
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, Dict, List

from prop_hunter_shared_utils import http_json, upsert_rows, safe_json_write, log, warn, norm_name, to_float

OUT = "prop_hunter_results_mlb_raw.json"

def innings_to_float(x):
    try:
        s = str(x)
        if "." not in s:
            return float(s)
        a, b = s.split(".", 1)
        return float(a) + float(b) / 3.0
    except Exception:
        return None

def schedule(date_str=None):
    date_str = date_str or datetime.utcnow().date().isoformat()
    data = http_json("https://statsapi.mlb.com/api/v1/schedule", params={"sportId": 1, "date": date_str, "hydrate": "team"}, retries=1) or {}
    games = []
    for d in data.get("dates", []) or []:
        games.extend(d.get("games", []) or [])
    return games

def boxscore(game_pk):
    return http_json(f"https://statsapi.mlb.com/api/v1/game/{game_pk}/boxscore", retries=1) or {}

def rows_from_boxscore(game) -> List[Dict[str, Any]]:
    gid = str(game.get("gamePk"))
    game_date = str(game.get("gameDate") or "")[:10]
    bs = boxscore(gid)
    rows = []
    teams = bs.get("teams") or {}
    for side in ("home", "away"):
        team_block = teams.get(side) or {}
        team_name = ((team_block.get("team") or {}).get("name"))
        opp_name = ((teams.get("away" if side == "home" else "home") or {}).get("team") or {}).get("name")
        for pid, p in (team_block.get("players") or {}).items():
            person = p.get("person") or {}
            name = person.get("fullName")
            if not name:
                continue
            batting = ((p.get("stats") or {}).get("batting") or {})
            pitching = ((p.get("stats") or {}).get("pitching") or {})
            if batting:
                rows.append({
                    "sport": "BASEBALL",
                    "league": "MLB",
                    "source": "mlb_statsapi_boxscore",
                    "source_game_id": gid,
                    "game_id": gid,
                    "game_date": game_date,
                    "player_name": name,
                    "normalized_name": norm_name(name),
                    "team": team_name,
                    "opponent": opp_name,
                    "hits": to_float(batting.get("hits")),
                    "total_bases": to_float(batting.get("totalBases")),
                    "home_runs": to_float(batting.get("homeRuns")),
                    "rbi": to_float(batting.get("rbi")),
                    "runs": to_float(batting.get("runs")),
                    "strikeouts_batter": to_float(batting.get("strikeOuts")),
                    "walks_batter": to_float(batting.get("baseOnBalls")),
                    "stolen_bases": to_float(batting.get("stolenBases")),
                    "raw": p,
                })
            if pitching:
                rows.append({
                    "sport": "BASEBALL",
                    "league": "MLB",
                    "source": "mlb_statsapi_boxscore",
                    "source_game_id": gid,
                    "game_id": gid,
                    "game_date": game_date,
                    "player_name": name,
                    "normalized_name": norm_name(name),
                    "team": team_name,
                    "opponent": opp_name,
                    "pitcher_strikeouts": to_float(pitching.get("strikeOuts")),
                    "pitcher_innings": innings_to_float(pitching.get("inningsPitched")),
                    "pitcher_hits_allowed": to_float(pitching.get("hits")),
                    "pitcher_earned_runs": to_float(pitching.get("earnedRuns")),
                    "pitcher_walks": to_float(pitching.get("baseOnBalls")),
                    "pitcher_home_runs_allowed": to_float(pitching.get("homeRuns")),
                    "raw": p,
                })
    return rows

def main():
    date_str = os.getenv("MLB_RESULT_DATE", "").strip() or datetime.utcnow().date().isoformat()
    games = schedule(date_str)
    rows = []
    for g in games[:int(os.getenv("MLB_RESULT_GAME_CAP", "30"))]:
        rows.extend(rows_from_boxscore(g))
    safe_json_write(OUT, rows)
    upsert_rows("prop_hunter_player_gamelogs", rows, "sport,league,game_id,normalized_name")
    log(f"MLB results done: games={len(games)} rows={len(rows)}")

if __name__ == "__main__":
    main()
