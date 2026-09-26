#!/usr/bin/env python3
"""PROP HUNTER — MLB official results/gamelogs for players in pending picks.

Design goals for the normal card/results paths:
- official MLB StatsAPI only; no browser and no paid key
- fetch ONLY players that still have pending MLB picks
- infer hitter/pitcher group from the stored market so we do not sweep the league
- persist schema-normalized rows into prop_hunter_player_gamelogs
- include doubles/triples so threshold markets settle against the exact stat
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Set, Tuple

from prop_hunter_shared_utils import (
    http_json,
    log,
    norm_name,
    safe_json_write,
    select_pick_rows,
    to_float,
    upsert_rows,
    warn,
)

OUT = "prop_hunter_results_mlb_raw.json"
SEARCH_URL = "https://statsapi.mlb.com/api/v1/people/search"
PEOPLE_URL = "https://statsapi.mlb.com/api/v1/people/{player_id}/stats"

PITCH_MARKET_TOKENS = (
    "pitcher", "strikeouts", "pitcher k", "outs recorded", "earned runs",
    "hits allowed", "walks allowed", "home runs allowed",
)


def current_season() -> str:
    return str(int(os.getenv("MLB_SEASON", str(datetime.now(timezone.utc).year))))


def _is_pending(row: Dict[str, Any]) -> bool:
    return str(row.get("status") or row.get("result") or "pending").strip().lower() in {
        "", "pending", "open", "none", "null"
    }


def _is_mlb(row: Dict[str, Any]) -> bool:
    sport = str(row.get("sport") or "").upper()
    league = str(row.get("league") or "").upper()
    return "MLB" in {sport, league} or sport == "BASEBALL"


def pending_player_groups(limit: int = 5000) -> List[Tuple[str, Set[str]]]:
    grouped: Dict[str, Tuple[str, Set[str]]] = {}
    for row in select_pick_rows(limit=limit):
        if not _is_mlb(row) or not _is_pending(row):
            continue
        player = str(row.get("player_name") or row.get("player") or "").strip()
        if not player:
            continue
        key = norm_name(player)
        market = str(row.get("market") or row.get("prop_type") or row.get("selection") or "").lower()
        group = "pitching" if any(tok in market for tok in PITCH_MARKET_TOKENS) else "hitting"
        if key not in grouped:
            grouped[key] = (player, set())
        grouped[key][1].add(group)

    cap = max(1, int(os.getenv("PH_MLB_RESULTS_MAX_PLAYERS", "40")))
    return list(grouped.values())[:cap]


def find_player(name: str) -> Dict[str, Any] | None:
    data = http_json(SEARCH_URL, params={"names": name}, retries=1) or {}
    people = data.get("people") or []
    if not people:
        return None
    wanted = norm_name(name)
    for p in people:
        if norm_name(p.get("fullName")) == wanted:
            return p
    for p in people:
        candidate = norm_name(p.get("fullName"))
        if candidate and (candidate in wanted or wanted in candidate):
            return p
    return None


def fetch_gamelog(player_id: int | str, group: str, season: str) -> List[Dict[str, Any]]:
    data = http_json(
        PEOPLE_URL.format(player_id=player_id),
        params={"stats": "gameLog", "group": group, "season": season, "hydrate": "team"},
        retries=1,
    ) or {}
    stats = data.get("stats") or []
    return (stats[0].get("splits") or []) if stats else []


def _game_id(split: Dict[str, Any]) -> str:
    game = split.get("game") or {}
    gid = game.get("gamePk") or game.get("id")
    if gid:
        return str(gid)
    raw = json.dumps(split, sort_keys=True, default=str)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:20]


def innings_value(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value))
    except Exception:
        return None


def base_row(name: str, split: Dict[str, Any], season: str) -> Dict[str, Any]:
    team = split.get("team") or {}
    opp = split.get("opponent") or {}
    gid = _game_id(split)
    return {
        "sport": "BASEBALL",
        "league": "MLB",
        "country": "USA",
        "season": season,
        "source": "mlb_statsapi",
        "source_game_id": gid,
        "game_id": gid,
        "game_date": str(split.get("date") or "")[:10] or None,
        "player_name": name,
        "normalized_name": norm_name(name),
        "team": team.get("abbreviation") or team.get("name"),
        "opponent": opp.get("abbreviation") or opp.get("name"),
        "home_away": "home" if split.get("isHome") is True else "away" if split.get("isHome") is False else None,
    }


def parse_hitting(name: str, split: Dict[str, Any], season: str) -> Dict[str, Any]:
    stat = split.get("stat") or {}
    row = base_row(name, split, season)
    row.update({
        "hits": to_float(stat.get("hits")),
        "doubles": to_float(stat.get("doubles")),
        "triples": to_float(stat.get("triples")),
        "total_bases": to_float(stat.get("totalBases")),
        "home_runs": to_float(stat.get("homeRuns")),
        "rbi": to_float(stat.get("rbi")),
        "runs": to_float(stat.get("runs")),
        "strikeouts_batter": to_float(stat.get("strikeOuts")),
        "walks_batter": to_float(stat.get("baseOnBalls")),
        "stolen_bases": to_float(stat.get("stolenBases")),
        "raw": {"group": "hitting", "split": split},
    })
    return row


def parse_pitching(name: str, split: Dict[str, Any], season: str) -> Dict[str, Any]:
    stat = split.get("stat") or {}
    row = base_row(name, split, season)
    row.update({
        "pitcher_strikeouts": to_float(stat.get("strikeOuts")),
        "pitcher_innings": innings_value(stat.get("inningsPitched")),
        "pitcher_hits_allowed": to_float(stat.get("hits")),
        "pitcher_earned_runs": to_float(stat.get("earnedRuns")),
        "pitcher_walks": to_float(stat.get("baseOnBalls")),
        "pitcher_home_runs_allowed": to_float(stat.get("homeRuns")),
        "raw": {"group": "pitching", "split": split},
    })
    return row


def merge_rows(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: Dict[Tuple[str, str, str, str, str], Dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row.get("sport") or ""), str(row.get("league") or ""),
            str(row.get("season") or ""), str(row.get("game_id") or ""),
            str(row.get("normalized_name") or ""),
        )
        if key not in merged:
            merged[key] = dict(row)
            continue
        current = merged[key]
        for k, v in row.items():
            if k == "raw":
                raw = current.get("raw")
                if not isinstance(raw, dict):
                    raw = {"previous": raw}
                raw[str((v or {}).get("group") if isinstance(v, dict) else "extra")] = v
                current["raw"] = raw
            elif v is not None:
                current[k] = v
    return list(merged.values())


def main() -> None:
    season = current_season()
    last_n = max(1, int(os.getenv("LAST_N_GAMES", "30")))
    requests = pending_player_groups(limit=int(os.getenv("MLB_PICK_SCAN_LIMIT", "5000")))
    rows: List[Dict[str, Any]] = []

    for player, groups in requests:
        try:
            person = find_player(player)
            if not person or not person.get("id"):
                warn(f"MLB player not resolved: {player}")
                continue
            canonical = person.get("fullName") or player
            for group in sorted(groups):
                splits = fetch_gamelog(person["id"], group, season)
                splits = sorted(splits, key=lambda x: str(x.get("date") or ""), reverse=True)[:last_n]
                parser = parse_pitching if group == "pitching" else parse_hitting
                rows.extend(parser(canonical, split, season) for split in splits)
        except Exception as exc:
            warn(f"MLB gamelog failed {player}: {exc}")

    rows = merge_rows(rows)
    safe_json_write(OUT, rows)
    if rows:
        upsert_rows(
            "prop_hunter_player_gamelogs",
            rows,
            "sport,league,season,game_id,normalized_name",
        )
    log(f"MLB results done: pending_players={len(requests)} rows={len(rows)}")


if __name__ == "__main__":
    main()
