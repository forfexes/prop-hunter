#!/usr/bin/env python3
"""
PROP HUNTER - american_props_scraper.py V9

Holt Player-Prop-Odds von The Odds API.

Neu:
- --sport all unterstützt MLB, WNBA, NBA, NFL
- schreibt alles gemeinsam in american_props_output.json
- kein Überschreiben pro Sport nötig

ENV:
ODDS_API_KEY
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests


BASE_URL = "https://api.the-odds-api.com/v4"

DEFAULT_SPORTS = [
    "baseball_mlb",
    "basketball_wnba",
    "basketball_nba",
    "americanfootball_nfl",
]

DEFAULT_MARKETS = {
    "baseball_mlb": [
        "batter_home_runs",
        "batter_hits",
        "batter_total_bases",
        "batter_rbis",
        "pitcher_strikeouts",
    ],
    "basketball_nba": [
        "player_points",
        "player_rebounds",
        "player_assists",
        "player_threes",
        "player_blocks",
        "player_steals",
        "player_points_rebounds_assists",
    ],
    "americanfootball_nfl": [
        "player_pass_tds",
        "player_pass_yds",
        "player_rush_yds",
        "player_receptions",
        "player_reception_yds",
        "player_anytime_td",
    ],
    "basketball_wnba": [
        "player_points",
        "player_rebounds",
        "player_assists",
        "player_threes",
        "player_points_rebounds_assists",
    ],
}


def get_api_keys() -> List[str]:
    raw = os.environ.get("ODDS_API_KEY") or os.environ.get("ODDS_API_KEYS") or ""
    keys = [k.strip() for k in raw.replace("\n", ",").split(",") if k.strip()]
    if not keys:
        raise RuntimeError("Fehlt: ODDS_API_KEY oder ODDS_API_KEYS")
    return keys


class KeyRing:
    def __init__(self, keys: List[str]):
        self.keys = keys
        self.i = 0

    @property
    def key(self) -> str:
        return self.keys[self.i % len(self.keys)]

    def rotate(self) -> None:
        self.i += 1


KEYRING = KeyRing(get_api_keys())


def get_json(url: str, params: dict, pause: float = 1.2) -> Optional[Any]:
    time.sleep(pause)
    for attempt in range(len(KEYRING.keys)):
        params = dict(params)
        params["apiKey"] = KEYRING.key
        try:
            r = requests.get(url, params=params, timeout=30)
            print(f"[GET] {r.status_code} {url}")
            if r.status_code == 200:
                return r.json()
            print(r.text[:300])
            if r.status_code in {401, 402, 403, 429}:
                KEYRING.rotate()
                continue
            return None
        except Exception as e:
            print(f"[ERROR] {url} -> {e}")
            KEYRING.rotate()
    return None


def american_to_decimal(price: Any) -> Optional[float]:
    try:
        price = float(price)
    except Exception:
        return None
    if price > 0:
        return round(1 + price / 100, 4)
    if price < 0:
        return round(1 + 100 / abs(price), 4)
    return None


def implied_probability_decimal(decimal_odds: Optional[float]) -> Optional[float]:
    if not decimal_odds or decimal_odds <= 1:
        return None
    return round(1 / decimal_odds, 4)


def normalize_outcome(
    sport: str,
    event: Dict[str, Any],
    bookmaker: Dict[str, Any],
    market: Dict[str, Any],
    outcome: Dict[str, Any],
) -> Dict[str, Any]:
    price = outcome.get("price")
    decimal_odds = american_to_decimal(price)

    return {
        "source": "the_odds_api",
        "sport": sport,
        "event_id": event.get("id"),
        "commence_time": event.get("commence_time"),
        "home_team": event.get("home_team"),
        "away_team": event.get("away_team"),
        "bookmaker": bookmaker.get("key"),
        "bookmaker_title": bookmaker.get("title"),
        "market_key": market.get("key"),
        "market_last_update": market.get("last_update"),
        "player_name": outcome.get("description") or outcome.get("name"),
        "selection": outcome.get("name"),
        "line": outcome.get("point"),
        "american_odds": price,
        "decimal_odds": decimal_odds,
        "implied_probability": implied_probability_decimal(decimal_odds),
        "raw": outcome,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def fetch_events(sport: str) -> List[Dict[str, Any]]:
    url = f"{BASE_URL}/sports/{sport}/events"
    data = get_json(url, {}) or []
    if not isinstance(data, list):
        return []
    return data


def fetch_event_props(
    sport: str,
    event_id: str,
    markets: List[str],
    regions: str = "us,eu",
    bookmakers: Optional[str] = None,
) -> Dict[str, Any]:
    url = f"{BASE_URL}/sports/{sport}/events/{event_id}/odds"
    params = {
        "regions": regions,
        "markets": ",".join(markets),
        "oddsFormat": "american",
    }
    if bookmakers:
        params["bookmakers"] = bookmakers

    data = get_json(url, params) or {}
    return data if isinstance(data, dict) else {}


def scrape_props(
    sport: str,
    markets: Optional[List[str]] = None,
    regions: str = "us,eu",
    bookmakers: Optional[str] = None,
    max_events: int = 20,
) -> List[Dict[str, Any]]:
    markets = markets or DEFAULT_MARKETS.get(sport, [])
    if not markets:
        print(f"[WARN] Keine Markets definiert für Sport: {sport}")
        return []

    events = fetch_events(sport)[:max_events]
    print(f"[INFO] {sport}: Events gefunden: {len(events)}")

    rows: List[Dict[str, Any]] = []

    for event in events:
        event_id = event.get("id")
        if not event_id:
            continue

        details = fetch_event_props(
            sport=sport,
            event_id=event_id,
            markets=markets,
            regions=regions,
            bookmakers=bookmakers,
        )

        event_context = {
            **event,
            "home_team": details.get("home_team") or event.get("home_team"),
            "away_team": details.get("away_team") or event.get("away_team"),
            "commence_time": details.get("commence_time") or event.get("commence_time"),
        }

        for bookmaker in details.get("bookmakers", []) or []:
            for market in bookmaker.get("markets", []) or []:
                for outcome in market.get("outcomes", []) or []:
                    row = normalize_outcome(
                        sport=sport,
                        event=event_context,
                        bookmaker=bookmaker,
                        market=market,
                        outcome=outcome,
                    )
                    if row.get("player_name") and row.get("decimal_odds"):
                        rows.append(row)

    print(f"[OK] {sport}: Props gesammelt: {len(rows)}")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sport", default="all", help="all, baseball_mlb, basketball_wnba, basketball_nba, americanfootball_nfl")
    parser.add_argument("--markets", help="Kommagetrennte Markets, sonst Default pro Sport")
    parser.add_argument("--regions", default="us,eu")
    parser.add_argument("--bookmakers", help="Optional z.B. draftkings,fanduel,pinnacle")
    parser.add_argument("--max-events", type=int, default=20)
    parser.add_argument("--output", default="american_props_output.json")
    args = parser.parse_args()

    sports = DEFAULT_SPORTS if args.sport == "all" else [args.sport]
    all_rows: List[Dict[str, Any]] = []

    for sport in sports:
        markets = [m.strip() for m in args.markets.split(",")] if args.markets and args.sport != "all" else None
        try:
            rows = scrape_props(
                sport=sport,
                markets=markets,
                regions=args.regions,
                bookmakers=args.bookmakers,
                max_events=args.max_events,
            )
            all_rows.extend(rows)
        except Exception as e:
            print(f"[WARN] {sport} failed: {e}")

    print(f"[OK] Gesamt Props gesammelt: {len(all_rows)}")

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(all_rows, f, ensure_ascii=False, indent=2)

    print(f"[OK] Gespeichert: {args.output}")


if __name__ == "__main__":
    main()
