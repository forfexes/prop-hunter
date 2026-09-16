#!/usr/bin/env python3
"""
PROP HUNTER — NBA RESULTS
=========================

Sources:
- nba_api PlayerGameLog
- ESPN scoreboard backup via public ESPN API

Writes:
- prop_hunter_player_gamelogs
- prop_hunter_results_raw.json
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from prop_hunter_shared_utils import (
    upsert_rows, safe_json_write, log, warn, norm_name, to_float, hash_key, http_json
)

OUT = "prop_hunter_results_nba_raw.json"

def current_nba_season(now=None):
    now = now or datetime.now(timezone.utc)
    start = now.year if now.month >= 10 else now.year - 1
    return f"{start}-{(start+1)%100:02d}"

def nba_api_player_logs(players=None, season=None, last_n=20) -> List[Dict[str, Any]]:
    try:
        from nba_api.stats.static import players as nba_players
        from nba_api.stats.endpoints import playergamelog
    except Exception as e:
        warn(f"nba_api unavailable: {e}")
        return []

    season = season or os.getenv("NBA_SEASON") or current_nba_season()
    wanted = {norm_name(x) for x in (players or []) if x}
    all_players = nba_players.get_players()
    selected = []
    for p in all_players:
        if not wanted or norm_name(p.get("full_name")) in wanted:
            selected.append(p)
    if wanted and not selected:
        for p in all_players:
            pn = norm_name(p.get("full_name"))
            if any(w in pn or pn in w for w in wanted):
                selected.append(p)

    # CRITICAL runtime guard: never sweep the complete historical NBA player list.
    # stats.nba.com can time out for 25s per player on GitHub runners; an empty
    # NBA_RESULT_PLAYERS used to mean "all players" and could burn 30+ minutes.
    if not wanted:
        log("NBA results: no explicit active-player list -> skip nba_api gamelog sweep")
        return []

    rows = []
    cap = int(os.getenv("NBA_RESULTS_PLAYER_CAP", "40"))
    api_timeout = int(os.getenv("NBA_RESULTS_TIMEOUT", "8"))
    for p in selected[:cap]:
        full = p.get("full_name")
        try:
            gl = playergamelog.PlayerGameLog(
                player_id=p.get("id"),
                season=season,
                season_type_all_star=os.getenv("NBA_SEASON_TYPE", "Regular Season"),
                timeout=api_timeout,
            )
            df = gl.get_data_frames()[0]
        except Exception as e:
            warn(f"NBA gamelog failed {full}: {e}")
            continue
        for _, r in df.head(last_n).iterrows():
            pts = to_float(r.get("PTS"), 0) or 0
            reb = to_float(r.get("REB"), 0) or 0
            ast = to_float(r.get("AST"), 0) or 0
            game_id = str(r.get("Game_ID") or r.get("GAME_ID"))
            rows.append({
                "sport": "BASKETBALL",
                "league": "NBA",
                "season": season,
                "source": "nba_api",
                "source_game_id": game_id,
                "game_id": game_id,
                "game_date": str(r.get("GAME_DATE"))[:10] if r.get("GAME_DATE") is not None else None,
                "player_name": full,
                "normalized_name": norm_name(full),
                "opponent": str(r.get("MATCHUP") or ""),
                "minutes": to_float(r.get("MIN")),
                "points": pts,
                "rebounds": reb,
                "assists": ast,
                "pra": pts + reb + ast,
                "ra": reb + ast,
                "threes_made": to_float(r.get("FG3M")),
                "steals": to_float(r.get("STL")),
                "blocks": to_float(r.get("BLK")),
                "turnovers": to_float(r.get("TOV")),
                "double_double": sum(1 for v in (pts, reb, ast) if v >= 10) >= 2,
                "triple_double": sum(1 for v in (pts, reb, ast) if v >= 10) >= 3,
                "raw": dict(r),
            })
    return rows

def espn_scoreboard(date_yyyymmdd: str | None = None) -> List[Dict[str, Any]]:
    date_yyyymmdd = date_yyyymmdd or datetime.utcnow().strftime("%Y%m%d")
    url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
    data = http_json(url, params={"dates": date_yyyymmdd}, retries=1) or {}
    rows = []
    for ev in data.get("events", []) or []:
        comp = (ev.get("competitions") or [{}])[0]
        for c in comp.get("competitors", []) or []:
            team = (c.get("team") or {}).get("displayName")
            for ath in c.get("statistics", []) or []:
                pass
        rows.append({
            "sport": "BASKETBALL",
            "league": "NBA",
            "source": "espn_scoreboard",
            "game_id": str(ev.get("id")),
            "source_game_id": str(ev.get("id")),
            "game_date": str(ev.get("date") or "")[:10],
            "raw": ev,
        })
    return rows

def main():
    names = [x.strip() for x in os.getenv("NBA_RESULT_PLAYERS", "").split(",") if x.strip()]
    rows = nba_api_player_logs(names, last_n=int(os.getenv("LAST_N_GAMES", "20")))
    rows.extend(espn_scoreboard())
    safe_json_write(OUT, rows)
    upsert_rows("prop_hunter_player_gamelogs", rows, "sport,league,season,game_id,normalized_name")
    log(f"NBA results done: {len(rows)} rows")

if __name__ == "__main__":
    main()
