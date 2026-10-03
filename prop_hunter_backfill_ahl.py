#!/usr/bin/env python3
"""Bounded AHL player-game backfill from the public HockeyTech feed.

Fetches players who have appeared in the current regular season, then combines
their current + previous regular-season game-by-game logs. The global gamelog
retention job keeps only the newest 40 games per player.
"""
from __future__ import annotations

import json
import os
import time
from collections import Counter
from typing import Any, Dict, Iterable, List

import requests

from prop_hunter_shared_utils import (
    hash_key, log, norm_name, select_rows, to_float, upsert_rows,
)

BASE = "https://lscluster.hockeytech.com/feed/index.php"
API_KEY = os.getenv("PH_AHL_HOCKEYTECH_KEY", "ccb91f29d6744675").strip()
CLIENT = "ahl"
LEAGUE_ID = "4"
SITE_ID = "3"
LEAGUE = "AHL"
SPORT = "ICE_HOCKEY"
KEEP = max(30, min(40, int(os.getenv("PH_AHL_LAST_N", "40"))))
PROFILE_LIMIT = max(25, min(600, int(os.getenv("PH_AHL_PROFILE_LIMIT", "250"))))
COOLDOWN = max(0.25, float(os.getenv("PH_AHL_COOLDOWN", "0.52")))
TIMEOUT = max(4, min(20, int(os.getenv("PH_AHL_TIMEOUT", "10"))))
BATCH = max(100, min(1000, int(os.getenv("PH_AHL_BATCH", "500"))))


def _clean_jsonp(text: str) -> Any:
    text = str(text or "").strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    if not starts:
        return None
    start = min(starts)
    end_char = "}" if text[start] == "{" else "]"
    end = text.rfind(end_char)
    if end < start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except Exception:
        return None


def _get(params: Dict[str, Any]) -> Any:
    payload = dict(params)
    payload.setdefault("key", API_KEY)
    payload.setdefault("client_code", CLIENT)
    payload.setdefault("league_id", LEAGUE_ID)
    try:
        r = requests.get(
            BASE,
            params=payload,
            timeout=TIMEOUT,
            headers={"Accept": "application/json,text/javascript,*/*", "User-Agent": "PROP-HUNTER/ahl-data"},
        )
        if r.status_code in {401, 403, 429}:
            log(f"AHL HockeyTech HTTP {r.status_code} view={payload.get('view')}")
            return None
        r.raise_for_status()
        return _clean_jsonp(r.text)
    except Exception as exc:
        log(f"AHL HockeyTech request failed view={payload.get('view')}: {type(exc).__name__}: {exc}")
        return None


def _sitekit(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, dict):
        value = payload.get("SiteKit")
        if isinstance(value, dict):
            return value
        return payload
    return {}


def _season_id(item: Any) -> int | None:
    if not isinstance(item, dict):
        return None
    for key in ("season_id", "seasonId", "id", "season"):
        try:
            value = int(str(item.get(key) or "").strip())
            if value > 0:
                return value
        except Exception:
            pass
    return None


def resolve_regular_seasons() -> List[int]:
    explicit = [x.strip() for x in os.getenv("PH_AHL_SEASONS", "").split(",") if x.strip()]
    if explicit:
        return [int(x) for x in explicit[:2]]

    payload = _get({
        "feed": "statviewfeed",
        "view": "bootstrap",
        "season": os.getenv("PH_AHL_BOOTSTRAP_SEASON", "90"),
        "pageName": "scorebar",
        "site_id": SITE_ID,
    })
    root = _sitekit(payload)
    values = root.get("regularSeasons") or root.get("regular_seasons") or []
    ids = sorted({sid for sid in (_season_id(x) for x in values) if sid}, reverse=True)
    if len(ids) >= 2:
        return ids[:2]

    current = None
    try:
        current = int(root.get("current_season_id") or 0)
    except Exception:
        current = None
    fallback = []
    if current:
        fallback.append(current)
        # HockeyTech commonly assigns the intervening playoff season the next id.
        if current >= 2:
            fallback.append(current - 2)
    for candidate in (92, 90):
        if candidate not in fallback:
            fallback.append(candidate)
    return fallback[:2]


def _unwrap_players(payload: Any) -> List[Dict[str, Any]]:
    root = _sitekit(payload)
    players = root.get("Players") or root.get("players")
    if isinstance(players, list):
        return [dict(x.get("row") or x) for x in players if isinstance(x, dict)]

    if isinstance(payload, list):
        out = []
        for top in payload:
            for section in (top.get("sections") or []) if isinstance(top, dict) else []:
                for item in section.get("data") or []:
                    if isinstance(item, dict):
                        row = item.get("row") or item
                        if isinstance(row, dict):
                            out.append(dict(row))
        return out
    return []


def current_players(season: int) -> List[Dict[str, Any]]:
    payload = _get({
        "feed": "statviewfeed",
        "view": "players",
        "season": season,
        "team": "all",
        "site_id": SITE_ID,
        "start": 0,
        "limit": 2000,
    })
    rows = _unwrap_players(payload)
    seen: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        pid = str(row.get("player_id") or row.get("playerId") or row.get("id") or "").strip()
        name = str(row.get("playerName") or row.get("name") or "").strip()
        gp = to_float(row.get("GP") if row.get("GP") is not None else row.get("games_played"), 0) or 0
        if not pid or not name or gp <= 0:
            continue
        item = dict(row)
        item["_player_id"] = pid
        item["_player_name"] = name
        item["_gp"] = gp
        seen[pid] = item
    return sorted(seen.values(), key=lambda r: (-float(r.get("_gp") or 0), r.get("_player_name") or ""))


def _game_rows(profile: Any) -> Iterable[Dict[str, Any]]:
    root = _sitekit(profile)
    gbg = root.get("gameByGame") or root.get("game_by_game") or []
    for block in gbg if isinstance(gbg, list) else []:
        if not isinstance(block, dict):
            continue
        for section in block.get("sections") or []:
            if not isinstance(section, dict):
                continue
            for item in section.get("data") or []:
                if isinstance(item, dict):
                    yield item


def _nested_game_id(item: Dict[str, Any], row: Dict[str, Any]) -> str:
    prop = item.get("prop") or {}
    if isinstance(prop, dict):
        game = prop.get("game") or {}
        if isinstance(game, dict):
            gid = game.get("gameLink") or game.get("game_link") or game.get("id")
            if gid:
                return str(gid)
        gid = prop.get("game.gameLink") or prop.get("gameLink")
        if gid:
            return str(gid)
    for key in ("game_id", "gameId", "game_link", "gameLink"):
        if row.get(key):
            return str(row.get(key))
    return ""


def fetch_profile(player_id: str, season: int) -> Any:
    data = _get({
        "feed": "statviewfeed",
        "view": "player",
        "player_id": player_id,
        "season_id": season,
        "site_id": SITE_ID,
        "lang": "en",
        "statsType": "standard",
    })
    time.sleep(COOLDOWN)
    return data


def existing_player_ids() -> Counter:
    rows = select_rows("prop_hunter_player_gamelogs", limit=None, filters={"league": LEAGUE}, order_by="id")
    counts: Counter = Counter()
    for row in rows:
        raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
        pid = str(raw.get("player_id") or "").strip()
        if pid:
            counts[pid] += 1
    return counts


def profile_to_rows(profile: Any, player: Dict[str, Any], season: int) -> List[Dict[str, Any]]:
    pid = str(player.get("_player_id") or "")
    name = str(player.get("_player_name") or "")
    team = player.get("teamCode") or player.get("team_code")
    out = []
    for item in _game_rows(profile):
        row = item.get("row") if isinstance(item.get("row"), dict) else item
        if not isinstance(row, dict):
            continue
        date = str(row.get("date_played") or row.get("date") or "")[:10]
        gid = _nested_game_id(item, row)
        game_label = str(row.get("game") or "")
        if not gid and date:
            gid = hash_key("AHL", pid, date, game_label)
        if not gid or not date:
            continue
        goals = to_float(row.get("goals"), 0) or 0
        assists = to_float(row.get("assists"), 0) or 0
        points = to_float(row.get("points"), goals + assists)
        if points is None:
            points = goals + assists
        out.append({
            "sport": SPORT,
            "league": LEAGUE,
            "season": str(season),
            "source": "ahl_hockeytech_profile",
            "source_game_id": gid,
            "game_id": gid,
            "game_date": date,
            "player_name": name,
            "normalized_name": norm_name(name),
            "team": team,
            "goals": goals,
            "assists_hockey": assists,
            "hockey_points": points,
            "shots_on_goal": to_float(row.get("shots")),
            "raw": {
                "player_id": pid,
                "game": game_label,
                "hockeytech_season_id": season,
                "plus_minus": row.get("plusminus"),
                "penalty_minutes": row.get("penalty_minutes"),
                "power_play_goals": row.get("pp"),
                "short_handed_goals": row.get("sh"),
                "game_winning_goals": row.get("gw"),
                "shootout_goals": row.get("shootout_goals"),
                "shootout_attempts": row.get("shootout_attempts"),
            },
        })
    return out


def main() -> None:
    seasons = resolve_regular_seasons()
    if not seasons:
        log("AHL backfill: no regular seasons resolved")
        return
    current, previous = seasons[0], seasons[1] if len(seasons) > 1 else seasons[0]
    players = current_players(current)
    existing = existing_player_ids()
    pending = [p for p in players if existing.get(str(p.get("_player_id")), 0) < 30][:PROFILE_LIMIT]
    log(f"AHL backfill seasons={seasons} current_players={len(players)} pending={len(pending)} limit={PROFILE_LIMIT}")

    rows: List[Dict[str, Any]] = []
    processed = 0
    for player in pending:
        pid = str(player.get("_player_id"))
        per_player: List[Dict[str, Any]] = []
        for season in dict.fromkeys((current, previous)):
            profile = fetch_profile(pid, season)
            if profile:
                per_player.extend(profile_to_rows(profile, player, season))
        # Keep only latest 40 before writing; global retention is the final guard.
        per_player.sort(key=lambda r: str(r.get("game_date") or ""), reverse=True)
        rows.extend(per_player[:KEEP])
        processed += 1
        if len(rows) >= BATCH:
            upsert_rows("prop_hunter_player_gamelogs", rows, "sport,league,season,game_id,normalized_name")
            rows.clear()
        if processed % 25 == 0:
            log(f"AHL backfill progress={processed}/{len(pending)}")

    if rows:
        upsert_rows("prop_hunter_player_gamelogs", rows, "sport,league,season,game_id,normalized_name")
    log(f"AHL backfill done processed_players={processed}")


if __name__ == "__main__":
    main()
