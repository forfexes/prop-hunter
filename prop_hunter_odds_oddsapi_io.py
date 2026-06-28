#!/usr/bin/env python3
"""
PROP HUNTER — ODDS-API.IO CONNECTOR
===================================

Env:
ODDSAPI_IO_KEY or ODDS_API_IO_KEY

Sicherer Connector:
- verschiedene mögliche Response-Strukturen werden normalisiert
- schreibt prop_hunter_prop_snapshots
- erzeugt lokale prop_hunter_oddsapi_io_props.json

Hinweis:
Endpoint-Pfade können je nach Anbieter/Plan variieren. Der Connector probiert mehrere übliche Pfade.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

from prop_hunter_shared_utils import (
    http_json, upsert_rows, safe_json_write, hash_key, now_iso, log, warn,
    norm_name, norm_market, to_float, american_to_decimal
)

BASE = os.getenv("ODDSAPI_IO_BASE", "https://api.odds-api.io/v3").rstrip("/")
OUT = "prop_hunter_oddsapi_io_props.json"

SPORT_KEYS = {
    "MLB": ["baseball_mlb", "mlb"],
    "NBA": ["basketball_nba", "nba"],
    "WNBA": ["basketball_wnba", "wnba"],
    "NFL": ["americanfootball_nfl", "nfl"],
    "NCAAF": ["americanfootball_ncaaf", "ncaaf"],
}

def key() -> str:
    return os.getenv("ODDSAPI_IO_KEY", "").strip() or os.getenv("ODDS_API_IO_KEY", "").strip()

def headers():
    k = key()
    return {"X-Api-Key": k, "Authorization": f"Bearer {k}"} if k else {}

def extract_items(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("data", "events", "games", "matches", "odds", "response"):
            if isinstance(data.get(k), list):
                return data[k]
        if isinstance(data.get("data"), dict):
            for k in ("events", "games", "odds"):
                if isinstance(data["data"].get(k), list):
                    return data["data"][k]
    return []

def normalize_prop(item: Dict[str, Any], sport: str, source_sport_key: str) -> List[Dict[str, Any]]:
    rows = []
    event_id = str(item.get("id") or item.get("event_id") or item.get("game_id") or item.get("match_id") or "")
    commence = item.get("commence_time") or item.get("start_time") or item.get("startTime") or item.get("date")
    home = item.get("home_team") or item.get("home") or item.get("homeTeam")
    away = item.get("away_team") or item.get("away") or item.get("awayTeam")

    # flat prop
    if item.get("player") or item.get("player_name") or item.get("selection"):
        player = item.get("player") or item.get("player_name") or item.get("selection")
        market = item.get("market") or item.get("market_name") or item.get("prop") or item.get("type")
        line = item.get("line") or item.get("point") or item.get("points") or item.get("handicap")
        odds = item.get("odds") or item.get("price") or item.get("decimal_odds")
        dec = to_float(odds) or american_to_decimal(odds)
        rows.append({
            "snapshot_id": hash_key("oddsapi_io", sport, event_id, player, market, line, dec),
            "source": "oddsapi_io",
            "sport": sport,
            "league": sport,
            "source_sport_key": source_sport_key,
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
            "odds_decimal": dec,
            "bookmaker": item.get("bookmaker") or item.get("sportsbook"),
            "raw": item,
            "created_at": now_iso(),
        })
        return rows

    # nested bookmakers/markets/outcomes
    for book in item.get("bookmakers", []) or item.get("sportsbooks", []) or []:
        book_name = book.get("key") or book.get("title") or book.get("name")
        for market in book.get("markets", []) or []:
            mkey = market.get("key") or market.get("name")
            for out in market.get("outcomes", []) or market.get("selections", []) or []:
                player = out.get("description") or out.get("player") or out.get("name")
                if not player:
                    continue
                line = out.get("point") or out.get("line")
                dec = to_float(out.get("price")) or to_float(out.get("decimal")) or american_to_decimal(out.get("odds"))
                rows.append({
                    "snapshot_id": hash_key("oddsapi_io", sport, event_id, player, mkey, line, dec, book_name),
                    "source": "oddsapi_io",
                    "sport": sport,
                    "league": sport,
                    "source_sport_key": source_sport_key,
                    "source_event_id": event_id,
                    "game_id": event_id,
                    "commence_time": commence,
                    "home_team": home,
                    "away_team": away,
                    "player_name": player,
                    "normalized_name": norm_name(player),
                    "market": mkey,
                    "market_key": norm_market(mkey),
                    "line": to_float(line),
                    "odds_decimal": dec,
                    "bookmaker": book_name,
                    "raw": out,
                    "created_at": now_iso(),
                })
    return rows

def fetch_for_sport(sport: str) -> List[Dict[str, Any]]:
    if not key():
        warn("ODDSAPI_IO_KEY missing")
        return []
    rows = []
    for sport_key in SPORT_KEYS.get(sport, [sport.lower()]):
        paths = [
            f"{BASE}/odds",
            f"{BASE}/sports/{sport_key}/odds",
            f"{BASE}/events/{sport_key}/odds",
            f"{BASE}/sports/{sport_key}/player-props",
        ]
        for url in paths:
            data = http_json(url, params={"sport": sport_key, "markets": "player_props"}, headers=headers(), retries=1)
            items = extract_items(data)
            if items:
                for it in items:
                    if isinstance(it, dict):
                        rows.extend(normalize_prop(it, sport, sport_key))
                log(f"odds-api.io {sport}: {len(rows)} props from {url}")
                return rows
    return rows

def main():
    all_rows = []
    for sport in os.getenv("PROP_HUNTER_SPORTS", "MLB,NBA,WNBA,NFL").split(","):
        sport = sport.strip().upper()
        if sport:
            all_rows.extend(fetch_for_sport(sport))
    safe_json_write(OUT, all_rows)
    upsert_rows("prop_hunter_prop_snapshots", all_rows, "snapshot_id")
    log(f"odds-api.io done: {len(all_rows)} props")

if __name__ == "__main__":
    main()
