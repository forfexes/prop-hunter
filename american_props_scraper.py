#!/usr/bin/env python3
"""
PROP HUNTER - american_props_scraper.py

Für American Sports:
- MLB
- NBA
- NFL
- NHL
- WNBA optional

Zweck:
- Holt Player-Prop-Odds von The Odds API.
- Normalisiert Props in ein einheitliches Format.
- Speichert JSON für Supabase Loader.

ENV:
ODDS_API_KEY

Beispiele:
python american_props_scraper.py --sport baseball_mlb
python american_props_scraper.py --sport basketball_nba
python american_props_scraper.py --sport americanfootball_nfl
python american_props_scraper.py --sport icehockey_nhl
"""

import argparse
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests


BASE_URL = "https://api.the-odds-api.com/v4"

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
    "icehockey_nhl": [
        "player_points",
        "player_power_play_points",
        "player_shots_on_goal",
        "player_assists",
    ],
    "basketball_wnba": [
        "player_points",
        "player_rebounds",
        "player_assists",
        "player_threes",
    ],
}


def get_api_key() -> str:
    key = os.environ.get("ODDS_API_KEY")
    if not key:
        raise RuntimeError("Fehlt: ODDS_API_KEY")
    return key


def get_json(url: str, params: dict, pause: float = 1.5) -> Optional[Any]:
    time.sleep(pause)
    try:
        r = requests.get(url, params=params, timeout=30)
        print(f"[GET] {r.status_code} {r.url}")
        if r.status_code != 200:
            print(r.text[:500])
            return None
        return r.json()
    except Exception as e:
        print(f"[ERROR] {url} -> {e}")
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


def fetch_events(sport: str, regions: str = "eu", odds_format: str = "american") -> List[Dict[str, Any]]:
    url = f"{BASE_URL}/sports/{sport}/events"
    params = {
        "apiKey": get_api_key(),
    }
    data = get_json(url, params) or []
    if not isinstance(data, list):
        return []
    return data


def fetch_event_props(
    sport: str,
    event_id: str,
    markets: List[str],
    regions: str = "eu",
    bookmakers: Optional[str] = None,
) -> Dict[str, Any]:
    url = f"{BASE_URL}/sports/{sport}/events/{event_id}/odds"
    params = {
        "apiKey": get_api_key(),
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
    regions: str = "eu",
    bookmakers: Optional[str] = None,
    max_events: int = 20,
) -> List[Dict[str, Any]]:
    markets = markets or DEFAULT_MARKETS.get(sport, [])
    if not markets:
        raise RuntimeError(f"Keine Markets definiert für Sport: {sport}")

    events = fetch_events(sport, regions=regions)[:max_events]
    print(f"[INFO] Events gefunden: {len(events)}")

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
                    rows.append(
                        normalize_outcome(
                            sport=sport,
                            event=event_context,
                            bookmaker=bookmaker,
                            market=market,
                            outcome=outcome,
                        )
                    )

    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sport", required=True, help="z.B. baseball_mlb, basketball_nba, americanfootball_nfl, icehockey_nhl")
    parser.add_argument("--markets", help="Kommagetrennte Markets, sonst Default pro Sport")
    parser.add_argument("--regions", default="eu")
    parser.add_argument("--bookmakers", help="Optional z.B. pinnacle,draftkings,fanduel")
    parser.add_argument("--max-events", type=int, default=20)
    parser.add_argument("--output", default="american_props_output.json")
    args = parser.parse_args()

    markets = [m.strip() for m in args.markets.split(",")] if args.markets else None

    rows = scrape_props(
        sport=args.sport,
        markets=markets,
        regions=args.regions,
        bookmakers=args.bookmakers,
        max_events=args.max_events,
    )

    print(f"[OK] Props gesammelt: {len(rows)}")

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    print(f"[OK] Gespeichert: {args.output}")


if __name__ == "__main__":
    main()
