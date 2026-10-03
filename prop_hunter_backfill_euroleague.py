#!/usr/bin/env python3
"""Bounded EuroLeague player-game backfill from the public EuroLeague v2 feed.

Initial mode loads current + previous season game boxscores and keeps at most
the newest 40 games per player. Later runs scan only recent/current-season games.
"""
from __future__ import annotations

import os
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List

import requests

from prop_hunter_shared_utils import log, norm_name, select_rows, to_float, upsert_rows

BASE = "https://api-live.euroleague.net/v2/competitions/E/seasons"
LEAGUE = "EUROLEAGUE"
SPORT = "BASKETBALL"
KEEP = max(30, min(40, int(os.getenv("PH_EUROLEAGUE_LAST_N", "40"))))
FULL_EVENT_CAP = max(250, min(500, int(os.getenv("PH_EUROLEAGUE_MAX_EVENTS", "430"))))
INCREMENTAL_EVENT_CAP = max(20, min(100, int(os.getenv("PH_EUROLEAGUE_INCREMENTAL_MAX_EVENTS", "50"))))
INITIAL_COMPLETE_ROWS = max(3000, int(os.getenv("PH_EUROLEAGUE_INITIAL_COMPLETE_ROWS", "5000")))
COOLDOWN = max(0.03, min(0.5, float(os.getenv("PH_EUROLEAGUE_COOLDOWN", "0.08"))))
TIMEOUT = max(5, min(30, int(os.getenv("PH_EUROLEAGUE_TIMEOUT", "12"))))
BATCH = max(100, min(1000, int(os.getenv("PH_EUROLEAGUE_BATCH", "500"))))
HEADERS = {"Accept": "application/json", "User-Agent": "PROP-HUNTER/euroleague-data"}


def _season_codes() -> List[str]:
    explicit = [x.strip().upper() for x in os.getenv("PH_EUROLEAGUE_SEASONS", "").split(",") if x.strip()]
    if explicit:
        return explicit[:2]
    now = datetime.now(timezone.utc)
    current = now.year if now.month >= 8 else now.year - 1
    return [f"E{current}", f"E{current-1}"]


def _get(url: str, params: Dict[str, Any] | None = None) -> Any:
    try:
        r = requests.get(url, params=params or {}, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code in {401, 403, 404, 429}:
            log(f"EuroLeague HTTP {r.status_code} {url}")
            return None
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        log(f"EuroLeague request failed {url}: {type(exc).__name__}: {exc}")
        return None


def existing_rows() -> List[Dict[str, Any]]:
    return select_rows(
        "prop_hunter_player_gamelogs",
        limit=None,
        filters={"league": LEAGUE},
        order_by="id",
    )


def season_games(season: str) -> List[Dict[str, Any]]:
    payload = _get(f"{BASE}/{season}/games", {"Limit": 1000, "Offset": 0})
    if not isinstance(payload, dict):
        return []
    rows = payload.get("data") or []
    out = []
    for game in rows if isinstance(rows, list) else []:
        if not isinstance(game, dict):
            continue
        played = game.get("played")
        status = str(game.get("gameStatus") or "").lower()
        if played is False or status in {"scheduled", "notstarted", "not_started"}:
            continue
        if game.get("gameCode") is None:
            continue
        out.append(game)
    return out


def game_stats(season: str, game_code: Any) -> Dict[str, Any]:
    payload = _get(f"{BASE}/{season}/games/{game_code}/stats")
    time.sleep(COOLDOWN)
    return payload if isinstance(payload, dict) else {}


def _name(player: Dict[str, Any]) -> str:
    person = player.get("person")
    if isinstance(person, str):
        return person.strip()
    if isinstance(person, dict):
        for key in ("name", "nameLatin", "displayName", "fullName"):
            if person.get(key):
                return str(person[key]).strip()
        first = str(person.get("firstName") or person.get("nameFirst") or "").strip()
        last = str(person.get("lastName") or person.get("nameLast") or "").strip()
        if first or last:
            return f"{first} {last}".strip()
    for key in ("name", "playerName", "displayName"):
        if player.get(key):
            return str(player[key]).strip()
    return ""


def _team(player: Dict[str, Any], side: Dict[str, Any]) -> str | None:
    club = player.get("club")
    if isinstance(club, str):
        return club.strip() or None
    if isinstance(club, dict):
        for key in ("name", "clubName", "clubPermanentName", "abbreviation", "code"):
            if club.get(key):
                return str(club[key]).strip()
    team = side.get("team")
    if isinstance(team, dict):
        for key in ("name", "clubName", "clubPermanentName", "abbreviation", "code"):
            if team.get(key):
                return str(team[key]).strip()
    return None


def _game_date(game: Dict[str, Any]) -> str:
    return str(game.get("date") or game.get("localDate") or "")[:10]


def _stat(stats: Dict[str, Any], *names: str) -> float | None:
    for name in names:
        if stats.get(name) not in (None, ""):
            return to_float(stats.get(name))
    return None


def parse_stats(payload: Dict[str, Any], season: str, game: Dict[str, Any]) -> List[Dict[str, Any]]:
    game_code = str(game.get("gameCode") or "")
    game_id = str(game.get("identifier") or f"{season}_{game_code}")
    date = _game_date(game)
    rows: List[Dict[str, Any]] = []
    for side_name in ("local", "road"):
        side = payload.get(side_name) or {}
        if not isinstance(side, dict):
            continue
        for item in side.get("players") or []:
            if not isinstance(item, dict):
                continue
            player = item.get("player") or {}
            stats = item.get("stats") or {}
            if not isinstance(player, dict) or not isinstance(stats, dict):
                continue
            name = _name(player)
            if not name:
                continue
            pts = _stat(stats, "points", "score")
            oreb = _stat(stats, "offensiveRebounds")
            dreb = _stat(stats, "defensiveRebounds")
            reb = _stat(stats, "totalRebounds", "rebounds")
            if reb is None and oreb is not None and dreb is not None:
                reb = oreb + dreb
            ast = _stat(stats, "assistances", "assists")
            threes = _stat(stats, "fieldGoalsMade3")
            stl = _stat(stats, "steals")
            blk = _stat(stats, "blocksFavour", "blocks")
            tov = _stat(stats, "turnovers")
            vals = [v for v in (pts, reb, ast, stl, blk) if v is not None]
            minutes_seconds = _stat(stats, "timePlayed")
            rows.append({
                "sport": SPORT,
                "league": LEAGUE,
                "country": "EU",
                "season": season,
                "source": "euroleague_v2_game_stats",
                "source_game_id": game_id,
                "game_id": game_id,
                "game_date": date or None,
                "player_name": name,
                "normalized_name": norm_name(name),
                "team": _team(player, side),
                "minutes": round(minutes_seconds / 60.0, 4) if minutes_seconds is not None else None,
                "points": pts,
                "rebounds": reb,
                "assists": ast,
                "pra": (pts + reb + ast) if None not in (pts, reb, ast) else None,
                "ra": (reb + ast) if None not in (reb, ast) else None,
                "pa": (pts + ast) if None not in (pts, ast) else None,
                "pr": (pts + reb) if None not in (pts, reb) else None,
                "threes_made": threes,
                "steals": stl,
                "blocks": blk,
                "turnovers": tov,
                "double_double": (sum(1 for v in vals if v >= 10) >= 2) if vals else None,
                "triple_double": (sum(1 for v in vals if v >= 10) >= 3) if vals else None,
                "raw": {
                    "competition": "E",
                    "season_code": season,
                    "game_code": game_code,
                    "side": side_name,
                    "player": player,
                    "valuation": stats.get("valuation"),
                    "field_goals_made_2": stats.get("fieldGoalsMade2"),
                    "field_goals_made_3": stats.get("fieldGoalsMade3"),
                    "free_throws_made": stats.get("freeThrowsMade"),
                    "offensive_rebounds": stats.get("offensiveRebounds"),
                    "defensive_rebounds": stats.get("defensiveRebounds"),
                },
            })
    return rows


def _all_games(seasons: Iterable[str]) -> List[tuple[str, Dict[str, Any]]]:
    out: List[tuple[str, Dict[str, Any]]] = []
    for season in seasons:
        games = season_games(season)
        log(f"EuroLeague {season}: completed_games={len(games)}")
        out.extend((season, g) for g in games)
    out.sort(key=lambda sg: (_game_date(sg[1]), int(sg[1].get("gameCode") or 0)), reverse=True)
    return out


def main() -> None:
    existing = existing_rows()
    full_mode = len(existing) < INITIAL_COMPLETE_ROWS
    seasons = _season_codes()
    games = _all_games(seasons)
    cap = FULL_EVENT_CAP if full_mode else INCREMENTAL_EVENT_CAP
    games = games[:cap]

    counts: Counter = Counter()
    if full_mode:
        for row in existing:
            nk = str(row.get("normalized_name") or "").strip()
            if nk:
                counts[nk] += 1

    log(
        f"EuroLeague backfill mode={'full' if full_mode else 'incremental'} "
        f"existing={len(existing)} seasons={seasons} events={len(games)} cap={cap}"
    )

    pending: List[Dict[str, Any]] = []
    processed = 0
    written = 0
    for season, game in games:
        payload = game_stats(season, game.get("gameCode"))
        rows = parse_stats(payload, season, game)
        if not rows:
            continue
        processed += 1
        for row in rows:
            nk = str(row.get("normalized_name") or "")
            if full_mode and counts.get(nk, 0) >= KEEP:
                continue
            pending.append(row)
            if full_mode:
                counts[nk] += 1
        if len(pending) >= BATCH:
            upsert_rows(
                "prop_hunter_player_gamelogs",
                pending,
                "sport,league,season,game_id,normalized_name",
            )
            written += len(pending)
            pending.clear()
        if processed % 50 == 0:
            log(f"EuroLeague backfill progress={processed}/{len(games)} written={written}")

    if pending:
        upsert_rows(
            "prop_hunter_player_gamelogs",
            pending,
            "sport,league,season,game_id,normalized_name",
        )
        written += len(pending)
    log(f"EuroLeague backfill done processed_events={processed} written_rows={written}")


if __name__ == "__main__":
    main()
