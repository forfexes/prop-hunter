#!/usr/bin/env python3
"""Backfill up to the last 40 NBA G League games per player."""
from __future__ import annotations

import os
from typing import Any, Dict, List

from prop_hunter_shared_utils import log, norm_name, to_float, upsert_rows

LEAGUE = "NBA_G_LEAGUE"
SPORT = "BASKETBALL"
KEEP = max(30, min(40, int(os.getenv("PH_GLEAGUE_LAST_N", "40"))))
BATCH = max(100, min(1000, int(os.getenv("PH_GLEAGUE_BATCH", "500"))))


def _season_candidates() -> List[str]:
    explicit = str(os.getenv("PH_GLEAGUE_SEASONS", "")).strip()
    if explicit:
        return [x.strip() for x in explicit.split(",") if x.strip()]
    return ["2026-27", "2025-26"]


def _row(record: Dict[str, Any], season: str) -> Dict[str, Any] | None:
    name = str(record.get("PLAYER_NAME") or "").strip()
    gid = str(record.get("GAME_ID") or "").strip()
    if not name or not gid:
        return None
    pts = to_float(record.get("PTS"), 0.0) or 0.0
    reb = to_float(record.get("REB"), 0.0) or 0.0
    ast = to_float(record.get("AST"), 0.0) or 0.0
    matchup = str(record.get("MATCHUP") or "")
    opponent = ""
    if " vs. " in matchup:
        opponent = matchup.split(" vs. ", 1)[1].strip()
    elif " @ " in matchup:
        opponent = matchup.split(" @ ", 1)[1].strip()
    return {
        "sport": SPORT,
        "league": LEAGUE,
        "season": str(record.get("SEASON_YEAR") or season),
        "source": "nba_stats_gleague",
        "source_game_id": gid,
        "game_id": gid,
        "game_date": str(record.get("GAME_DATE") or "")[:10],
        "player_name": name,
        "normalized_name": norm_name(name),
        "team": record.get("TEAM_ABBREVIATION") or record.get("TEAM_NAME"),
        "opponent": opponent or None,
        "minutes": to_float(record.get("MIN")),
        "points": pts,
        "rebounds": reb,
        "assists": ast,
        "pra": pts + reb + ast,
        "ra": reb + ast,
        "pa": pts + ast,
        "pr": pts + reb,
        "threes_made": to_float(record.get("FG3M")),
        "steals": to_float(record.get("STL")),
        "blocks": to_float(record.get("BLK")),
        "turnovers": to_float(record.get("TOV")),
        "double_double": bool((to_float(record.get("DD2"), 0) or 0) >= 1),
        "triple_double": bool((to_float(record.get("TD3"), 0) or 0) >= 1),
        "raw": {
            "player_id": record.get("PLAYER_ID"),
            "team_id": record.get("TEAM_ID"),
            "matchup": matchup,
            "wl": record.get("WL"),
            "fgm": record.get("FGM"),
            "fga": record.get("FGA"),
            "fg3a": record.get("FG3A"),
            "ftm": record.get("FTM"),
            "fta": record.get("FTA"),
            "oreb": record.get("OREB"),
            "dreb": record.get("DREB"),
            "pf": record.get("PF"),
            "plus_minus": record.get("PLUS_MINUS"),
            "fantasy_points": record.get("NBA_FANTASY_PTS"),
            "last_n_requested": KEEP,
        },
    }


def fetch_season(season: str) -> List[Dict[str, Any]]:
    from nba_api.stats.endpoints import playergamelogs
    ep = playergamelogs.PlayerGameLogs(
        league_id_nullable="20",
        season_nullable=season,
        season_type_nullable="Regular Season",
        last_n_games_nullable=KEEP,
        timeout=45,
    )
    frames = ep.get_data_frames()
    if not frames:
        return []
    df = frames[0]
    if df is None or df.empty:
        return []
    rows = []
    for record in df.to_dict("records"):
        item = _row(record, season)
        if item:
            rows.append(item)
    return rows


def main() -> None:
    rows: List[Dict[str, Any]] = []
    used_season = ""
    errors = []
    for season in _season_candidates():
        try:
            candidate = fetch_season(season)
        except Exception as exc:
            errors.append(f"{season}:{type(exc).__name__}:{exc}")
            log(f"G League {season} fetch failed: {type(exc).__name__}: {exc}")
            continue
        log(f"G League {season}: rows={len(candidate)}")
        if candidate:
            rows = candidate
            used_season = season
            break

    if not rows:
        log(f"G League backfill empty errors={errors[:2]}")
        return

    dedup = {}
    for row in rows:
        key = (
            row.get("sport"), row.get("league"), row.get("season"),
            row.get("game_id"), row.get("normalized_name"),
        )
        dedup[key] = row
    rows = list(dedup.values())

    for start in range(0, len(rows), BATCH):
        upsert_rows(
            "prop_hunter_player_gamelogs",
            rows[start:start + BATCH],
            "sport,league,season,game_id,normalized_name",
        )
    players = len({r.get("normalized_name") for r in rows})
    games = len({r.get("game_id") for r in rows})
    log(f"G League backfill done season={used_season} rows={len(rows)} players={players} games={games}")


if __name__ == "__main__":
    main()
