#!/usr/bin/env python3
"""
PROP HUNTER — WNBA RESULTS
==========================

Sources:
- ESPN public scoreboard/summary fallback
- wehoop/sportsdataverse-style data vorbereitet, wenn später installiert/verfügbar

Writes:
- prop_hunter_player_gamelogs
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from prop_hunter_shared_utils import http_json, upsert_rows, safe_json_write, log, warn, norm_name, to_float, hash_key

OUT = "prop_hunter_results_wnba_raw.json"

def _wnba_season(date_value: str | None = None) -> str:
    """WNBA seasons are calendar-year seasons (e.g. 2026), not NBA-style 2025-26."""
    env = str(os.getenv("WNBA_SEASON") or "").strip()
    if env:
        return env
    raw = str(date_value or "")
    m = __import__("re").search(r"(20\d{2})", raw)
    if m:
        return m.group(1)
    return str(datetime.now(timezone.utc).year)


def espn_scoreboard(date_yyyymmdd: str | None = None) -> List[Dict[str, Any]]:
    date_yyyymmdd = date_yyyymmdd or datetime.utcnow().strftime("%Y%m%d")
    url = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard"
    data = http_json(url, params={"dates": date_yyyymmdd}, retries=1) or {}
    games = []
    for ev in data.get("events", []) or []:
        game_date = str(ev.get("date") or "")[:10]
        games.append({
            "sport": "BASKETBALL",
            "league": "WNBA",
            "season": _wnba_season(game_date),
            "source": "espn_scoreboard",
            "game_id": str(ev.get("id")),
            "source_game_id": str(ev.get("id")),
            "game_date": game_date,
            "raw": ev,
        })
    return games

def espn_summary_players(game_id: str) -> List[Dict[str, Any]]:
    url = "https://site.web.api.espn.com/apis/site/v2/sports/basketball/wnba/summary"
    data = http_json(url, params={"event": game_id}, retries=1) or {}
    rows = []
    box = data.get("boxscore") or {}
    for team_block in box.get("players", []) or []:
        team = ((team_block.get("team") or {}).get("displayName") or (team_block.get("team") or {}).get("shortDisplayName"))
        stats_groups = team_block.get("statistics", []) or []
        for group in stats_groups:
            labels = group.get("labels") or []
            for ath in group.get("athletes", []) or []:
                athlete = ath.get("athlete") or {}
                name = athlete.get("displayName")
                if not name:
                    continue
                vals = ath.get("stats") or []
                stat_map = {labels[i]: vals[i] for i in range(min(len(labels), len(vals)))}
                pts = to_float(stat_map.get("PTS"), 0) or 0
                reb = to_float(stat_map.get("REB"), 0) or 0
                ast = to_float(stat_map.get("AST"), 0) or 0
                game_date = str((data.get("header") or {}).get("competitions", [{}])[0].get("date") or "")[:10]
                rows.append({
                    "sport": "BASKETBALL",
                    "league": "WNBA",
                    "season": _wnba_season(game_date),
                    "source": "espn_summary",
                    "source_game_id": str(game_id),
                    "game_id": str(game_id),
                    "game_date": game_date,
                    "player_name": name,
                    "normalized_name": norm_name(name),
                    "team": team,
                    "minutes": to_float(stat_map.get("MIN")),
                    "points": pts,
                    "rebounds": reb,
                    "assists": ast,
                    "pra": pts + reb + ast,
                    "ra": reb + ast,
                    "threes_made": to_float(stat_map.get("3PM") or stat_map.get("3PT")),
                    "steals": to_float(stat_map.get("STL")),
                    "blocks": to_float(stat_map.get("BLK")),
                    "turnovers": to_float(stat_map.get("TO") or stat_map.get("TOV")),
                    "double_double": sum(1 for v in (pts, reb, ast) if v >= 10) >= 2,
                    "triple_double": sum(1 for v in (pts, reb, ast) if v >= 10) >= 3,
                    "raw": {"stat_map": stat_map, "athlete": athlete},
                })
    return rows

def main():
    games = espn_scoreboard(os.getenv("WNBA_RESULT_DATE"))
    rows = list(games)
    for g in games[:int(os.getenv("WNBA_RESULT_GAME_CAP", "20"))]:
        rows.extend(espn_summary_players(g["game_id"]))
    safe_json_write(OUT, rows)
    upsert_rows("prop_hunter_player_gamelogs", rows, "sport,league,season,game_id,normalized_name")
    log(f"WNBA results done: {len(rows)} rows")

if __name__ == "__main__":
    main()
