#!/usr/bin/env python3
"""PROP HUNTER — NFL results and player gamelog collector.

Sources:
- ESPN public scoreboard/summary
- nflverse remains available to the feature pipeline separately

Writes:
- prop_hunter_player_gamelogs
- prop_hunter_results_nfl_raw.json
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from prop_hunter_shared_utils import (
    hash_key, http_json, log, norm_name, safe_json_write, to_float,
    upsert_rows, warn,
)

OUT = "prop_hunter_results_nfl_raw.json"


def _number(mapping: Dict[str, Any], *keys: str) -> float:
    for key in keys:
        value = mapping.get(key.upper())
        if value not in (None, ""):
            try:
                return float(str(value).split("/")[0])
            except Exception:
                continue
    return 0.0


def collect(date_yyyymmdd: str | None = None) -> List[Dict[str, Any]]:
    date_yyyymmdd = date_yyyymmdd or (
        datetime.now(timezone.utc) - timedelta(days=1)
    ).strftime("%Y%m%d")
    scoreboard = http_json(
        "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
        params={"dates": date_yyyymmdd},
        retries=1,
    ) or {}

    rows: List[Dict[str, Any]] = []
    for event in scoreboard.get("events", []) or []:
        event_id = str(event.get("id") or "")
        if not event_id:
            continue
        summary = http_json(
            "https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary",
            params={"event": event_id},
            retries=1,
        ) or {}
        game_date = str(event.get("date") or "")[:10]

        player_rows: Dict[str, Dict[str, Any]] = {}
        for team in (summary.get("boxscore") or {}).get("players", []) or []:
            team_name = ((team.get("team") or {}).get("displayName") or "")
            for group in team.get("statistics", []) or []:
                group_name = str(group.get("name") or group.get("displayName") or "").lower()
                labels = [str(x).upper() for x in group.get("labels", [])]
                for athlete in group.get("athletes", []) or []:
                    athlete_info = athlete.get("athlete") or {}
                    player = athlete_info.get("displayName") or ""
                    if not player:
                        continue
                    key = norm_name(player)
                    row = player_rows.setdefault(key, {
                        "sport": "AMERICAN_FOOTBALL",
                        "league": "NFL",
                        "season": str(datetime.now(timezone.utc).year),
                        "source": "espn",
                        "source_game_id": event_id,
                        "game_id": event_id,
                        "game_date": game_date,
                        "player_name": player,
                        "normalized_name": key,
                        "team": team_name,
                        "passing_yards": 0.0,
                        "passing_completions": 0.0,
                        "passing_attempts": 0.0,
                        "passing_touchdowns": 0.0,
                        "interceptions_thrown": 0.0,
                        "rushing_yards": 0.0,
                        "rushing_attempts": 0.0,
                        "rushing_touchdowns": 0.0,
                        "receiving_yards": 0.0,
                        "receptions": 0.0,
                        "receiving_touchdowns": 0.0,
                        "longest_reception": 0.0,
                        "defensive_sacks": 0.0,
                        "tackles": 0.0,
                        "tackle_assists": 0.0,
                        "kicking_points": 0.0,
                        "field_goals_made": 0.0,
                        "longest_field_goal": 0.0,
                        "longest_punt": 0.0,
                        "raw": {},
                    })
                    stat_map = dict(zip(labels, athlete.get("stats", []) or []))

                    if "passing" in group_name:
                        cmp_att = stat_map.get("C/ATT") or stat_map.get("CMP/ATT")
                        if cmp_att and "/" in str(cmp_att):
                            try:
                                cmp_v, att_v = str(cmp_att).split("/", 1)
                                row["passing_completions"] += float(cmp_v)
                                row["passing_attempts"] += float(att_v)
                            except Exception:
                                pass
                        row["passing_yards"] += _number(stat_map, "YDS")
                        row["passing_touchdowns"] += _number(stat_map, "TD")
                        row["interceptions_thrown"] += _number(stat_map, "INT")
                    elif "rushing" in group_name:
                        row["rushing_attempts"] += _number(stat_map, "CAR", "ATT")
                        row["rushing_yards"] += _number(stat_map, "YDS")
                        row["rushing_touchdowns"] += _number(stat_map, "TD")
                    elif "receiving" in group_name:
                        row["receptions"] += _number(stat_map, "REC")
                        row["receiving_yards"] += _number(stat_map, "YDS")
                        row["receiving_touchdowns"] += _number(stat_map, "TD")
                        row["longest_reception"] = max(
                            row["longest_reception"], _number(stat_map, "LONG", "LNG")
                        )
                    elif "defensive" in group_name:
                        row["defensive_sacks"] += _number(stat_map, "SACKS", "SACK")
                        row["tackles"] += _number(stat_map, "TOT", "TOTAL", "TACKLES")
                        row["tackle_assists"] += _number(stat_map, "AST", "ASSISTS")
                    elif "kicking" in group_name:
                        row["kicking_points"] += _number(stat_map, "PTS")
                        row["longest_field_goal"] = max(
                            row["longest_field_goal"], _number(stat_map, "LONG", "LNG")
                        )
                        fg = stat_map.get("FG") or stat_map.get("FGM/FGA")
                        if fg and "/" in str(fg):
                            try:
                                row["field_goals_made"] += float(str(fg).split("/", 1)[0])
                            except Exception:
                                pass
                        else:
                            row["field_goals_made"] += _number(stat_map, "FGM")
                    elif "punting" in group_name:
                        row["longest_punt"] = max(
                            row["longest_punt"], _number(stat_map, "LONG", "LNG")
                        )
                    row["raw"][group_name or "unknown"] = stat_map

        for row in player_rows.values():
            row["rush_receiving_yards"] = (
                row["rushing_yards"] + row["receiving_yards"]
            )
            row["touchdowns"] = (
                row["rushing_touchdowns"] + row["receiving_touchdowns"]
            )
            row["row_id"] = hash_key(
                "NFL", event_id, row["normalized_name"], game_date
            )
            rows.append(row)

    return rows


def main() -> None:
    rows = collect()
    safe_json_write(OUT, rows)
    upsert_rows(
        "prop_hunter_player_gamelogs",
        rows,
        "sport,league,season,game_id,normalized_name",
    )
    log(f"NFL results done: {len(rows)} rows")


if __name__ == "__main__":
    main()
