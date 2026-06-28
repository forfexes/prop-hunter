#!/usr/bin/env python3
"""
PROP HUNTER — SPORTSGAMEODDS CONNECTOR
======================================

Env:
SPORTSGAMEODDS_API_KEY

Normalisiert Player Props und schreibt prop_hunter_prop_snapshots.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

from prop_hunter_shared_utils import (
    http_json, upsert_rows, safe_json_write, hash_key, now_iso, log, warn,
    norm_name, norm_market, to_float, american_to_decimal
)

BASE = os.getenv("SPORTSGAMEODDS_BASE", "https://api.sportsgameodds.com/v1").rstrip("/")
OUT = "prop_hunter_sportsgameodds_props.json"

SPORT_KEYS = {
    "MLB": "baseball_mlb",
    "NBA": "basketball_nba",
    "WNBA": "basketball_wnba",
    "NFL": "football_nfl",
    "NCAAF": "football_ncaaf",
}

def key() -> str:
    return os.getenv("SPORTSGAMEODDS_API_KEY", "").strip()

def headers():
    return {"X-Api-Key": key(), "Authorization": f"Bearer {key()}"} if key() else {}

def extract_items(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("data", "odds", "events", "markets", "response"):
            if isinstance(data.get(k), list):
                return data[k]
    return []

def normalize(item: Dict[str, Any], sport: str, sport_key: str) -> List[Dict[str, Any]]:
    rows = []
    event_id = str(item.get("eventID") or item.get("event_id") or item.get("gameID") or item.get("id") or "")
    home = item.get("homeTeam") or item.get("home_team")
    away = item.get("awayTeam") or item.get("away_team")
    commence = item.get("startTime") or item.get("commence_time") or item.get("date")

    # flat odds
    player = item.get("playerName") or item.get("player") or item.get("participantName") or item.get("selection")
    market = item.get("marketName") or item.get("market") or item.get("propName") or item.get("stat")
    if player and market:
        line = item.get("line") or item.get("points") or item.get("handicap")
        odds = item.get("odds") or item.get("price") or item.get("decimalOdds")
        rows.append({
            "snapshot_id": hash_key("sportsgameodds", sport, event_id, player, market, line, odds),
            "source": "sportsgameodds",
            "sport": sport,
            "league": sport,
            "source_sport_key": sport_key,
            "source_event_id": event_id,
            "game_id": event_id,
            "commence_time": commence,
            "home_team": home,
            "away_team": away,
            "player_name": player,
            "normalized_name": norm_name(player),
            "market": market,
            "market_key": norm_market(market),
            "line": to_float(line),
            "odds_decimal": to_float(odds) or american_to_decimal(odds),
            "bookmaker": item.get("sportsbook") or item.get("bookmaker") or item.get("book"),
            "raw": item,
            "created_at": now_iso(),
        })
        return rows

    # nested
    for market_obj in item.get("markets", []) or []:
        m = market_obj.get("name") or market_obj.get("key")
        for sel in market_obj.get("selections", []) or market_obj.get("outcomes", []) or []:
            p = sel.get("playerName") or sel.get("player") or sel.get("name")
            if not p:
                continue
            line = sel.get("line") or sel.get("points")
            odds = sel.get("odds") or sel.get("price")
            rows.append({
                "snapshot_id": hash_key("sportsgameodds", sport, event_id, p, m, line, odds),
                "source": "sportsgameodds",
                "sport": sport,
                "league": sport,
                "source_sport_key": sport_key,
                "source_event_id": event_id,
                "game_id": event_id,
                "commence_time": commence,
                "home_team": home,
                "away_team": away,
                "player_name": p,
                "normalized_name": norm_name(p),
                "market": m,
                "market_key": norm_market(m),
                "line": to_float(line),
                "odds_decimal": to_float(odds) or american_to_decimal(odds),
                "bookmaker": sel.get("sportsbook") or sel.get("bookmaker"),
                "raw": sel,
                "created_at": now_iso(),
            })
    return rows

def fetch_sport(sport: str) -> List[Dict[str, Any]]:
    if not key():
        warn("SPORTSGAMEODDS_API_KEY missing")
        return []
    sport_key = SPORT_KEYS.get(sport, sport.lower())
    rows = []
    paths = [
        f"{BASE}/odds",
        f"{BASE}/events",
        f"{BASE}/markets",
        f"{BASE}/player-props",
    ]
    params_list = [
        {"sportID": sport_key, "marketType": "player"},
        {"sport": sport_key, "type": "player-props"},
        {"league": sport_key, "includePlayerProps": "true"},
    ]
    for url in paths:
        for params in params_list:
            data = http_json(url, params=params, headers=headers(), retries=1)
            items = extract_items(data)
            if items:
                for it in items:
                    if isinstance(it, dict):
                        rows.extend(normalize(it, sport, sport_key))
                log(f"sportsgameodds {sport}: {len(rows)} props from {url}")
                return rows
    return rows

def main():
    rows = []
    for sport in os.getenv("PROP_HUNTER_SPORTS", "MLB,NBA,WNBA,NFL").split(","):
        sport = sport.strip().upper()
        if sport:
            rows.extend(fetch_sport(sport))
    safe_json_write(OUT, rows)
    upsert_rows("prop_hunter_prop_snapshots", rows, "snapshot_id")
    log(f"sportsgameodds done: {len(rows)} props")

if __name__ == "__main__":
    main()
