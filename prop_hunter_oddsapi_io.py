#!/usr/bin/env python3
"""Odds-API.io v3 player-prop adapter for PROP HUNTER.

Current API flow (v3):
  1) /events?sport=<slug> -> event ids
  2) /odds?eventId=<id>   -> bookmaker markets, including player props

The adapter is key-gated and bounded for GitHub Actions. It never invents a price.
"""
from __future__ import annotations

import math
import os
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

API_BASE = os.getenv("ODDSAPI_IO_BASE", "https://api.odds-api.io/v3").rstrip("/")
API_KEY = (os.getenv("ODDSAPI_IO_KEY") or os.getenv("ODDS_API_IO_KEY") or "").strip()
TIMEOUT = max(3, min(12, int(os.getenv("PH_ODDSAPI_IO_TIMEOUT", "6"))))
MAX_EVENTS = max(1, min(8, int(os.getenv("PH_ODDSAPI_IO_MAX_EVENTS", "3"))))
BOOKMAKERS = (os.getenv("PH_ODDSAPI_IO_BOOKMAKERS") or "").strip()

SPORT_SLUG = {
    "MLB": "mlb",
    "NBA": "nba",
    "NFL": "nfl",
    "NHL": "nhl",
    # Odds-API.io documents the major-league slugs directly. These aliases are
    # intentionally optional; if a tenant does not expose them, they simply return 0.
    "WNBA": "wnba",
    "NCAAB": "ncaab",
    "NCAAF": "ncaaf",
}


def configured() -> bool:
    return bool(API_KEY)


def _f(value: Any) -> Optional[float]:
    try:
        v = float(value)
        return v if math.isfinite(v) else None
    except Exception:
        return None


def _norm_market(value: Any) -> str:
    s = str(value or "").strip().lower()
    s = s.replace("3-pointers", "threes").replace("3 pointers", "threes")
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    aliases = {
        "points": "player_points",
        "rebounds": "player_rebounds",
        "assists": "player_assists",
        "threes": "player_threes",
        "three_pointers": "player_threes",
        "passing_yards": "player_pass_yards",
        "passing_touchdowns": "player_pass_tds",
        "rushing_yards": "player_rush_yards",
        "receiving_yards": "player_receiving_yards",
        "receptions": "player_receptions",
        "strikeouts": "pitcher_strikeouts",
        "pitcher_strikeouts": "pitcher_strikeouts",
        "home_runs": "batter_home_runs",
        "total_bases": "batter_total_bases",
        "hits": "batter_hits",
        "shots_on_goal": "player_shots_on_goal",
        "saves": "player_saves",
        "goals": "player_goals",
    }
    return aliases.get(s, s or "player_prop")


def _split_label(label: str, market_name: str = "") -> Tuple[str, str]:
    """Extract player + stat from labels like 'LeBron James - Points'."""
    text = str(label or "").strip()
    for sep in (" - ", " – ", " — ", ": "):
        if sep in text:
            left, right = text.rsplit(sep, 1)
            if left.strip() and right.strip():
                return left.strip(), right.strip()
    # Some responses expose the stat at market level and only the player in label.
    if text and market_name and "player" in market_name.lower():
        cleaned = re.sub(r"\bplayer\s*props?\b", "", market_name, flags=re.I).strip(" -:")
        return text, cleaned or market_name
    return "", ""


def parse_odds_payload(payload: Dict[str, Any], sport: str) -> List[Dict[str, Any]]:
    """Normalize one /v3/odds payload. Supports current and common variant shapes."""
    if not isinstance(payload, dict):
        return []
    event_id = str(payload.get("id") or payload.get("eventId") or payload.get("event_id") or "")
    home = str(payload.get("home") or payload.get("home_team") or "")
    away = str(payload.get("away") or payload.get("away_team") or "")
    commence = str(payload.get("date") or payload.get("commence_time") or payload.get("startTime") or "")
    league_obj = payload.get("league") or {}
    league = str(league_obj.get("name") if isinstance(league_obj, dict) else league_obj or sport).upper()
    books = payload.get("bookmakers") or {}
    if isinstance(books, list):
        books = {str(x.get("name") or x.get("key") or f"book_{i}"): x.get("markets") or x.get("odds") or [] for i, x in enumerate(books) if isinstance(x, dict)}
    if not isinstance(books, dict):
        return []

    rows: List[Dict[str, Any]] = []
    for book, markets in books.items():
        if isinstance(markets, dict):
            markets = markets.get("markets") or markets.get("odds") or []
        if not isinstance(markets, list):
            continue
        for market in markets:
            if not isinstance(market, dict):
                continue
            market_name = str(market.get("name") or market.get("label") or market.get("market") or "")
            odds_list = market.get("odds") or market.get("outcomes") or []
            if not isinstance(odds_list, list):
                continue
            for odd in odds_list:
                if not isinstance(odd, dict):
                    continue
                label = str(odd.get("label") or odd.get("player") or odd.get("name") or "")
                player = str(odd.get("player") or odd.get("playerName") or "").strip()
                stat = str(odd.get("stat") or odd.get("market") or "").strip()
                if not player:
                    player, parsed_stat = _split_label(label, market_name)
                    stat = stat or parsed_stat
                if not player:
                    continue
                market_key = _norm_market(stat or market_name)
                line = _f(odd.get("hdp") if odd.get("hdp") is not None else odd.get("line"))

                # Current documented format exposes over/under side prices in one row.
                side_pairs = []
                for side in ("over", "under", "yes", "no"):
                    price = _f(odd.get(side))
                    if price and price > 1:
                        side_pairs.append((side, price))
                # Generic outcome format fallback.
                if not side_pairs:
                    price = _f(odd.get("price") or odd.get("odds") or odd.get("decimalOdds"))
                    side = str(odd.get("side") or odd.get("outcome") or "").lower().strip()
                    if price and price > 1 and side in {"over", "under", "yes", "no"}:
                        side_pairs.append((side, price))
                if not side_pairs:
                    continue
                if line is None:
                    # Binary props such as HR/TD/goal are modelled as 0.5 thresholds.
                    line = 0.5 if any(s in {"yes", "no"} for s, _ in side_pairs) else None
                if line is None:
                    continue
                for side, price in side_pairs:
                    direction = "over" if side == "yes" else "under" if side == "no" else side
                    rows.append({
                        "source": "oddsapi_io",
                        "bookmaker": str(book).lower(),
                        "sport": sport,
                        "league": sport if sport in {"MLB", "NBA", "WNBA", "NFL", "NHL", "NCAAB", "NCAAF"} else league,
                        "source_event_id": event_id,
                        "event_id": event_id,
                        "commence_time": commence,
                        "home_team": home,
                        "away_team": away,
                        "player_name": player,
                        "market": market_key,
                        "market_key": market_key,
                        "direction": direction,
                        "line": line,
                        "odds_decimal": round(float(price), 4),
                        "selection": side.title(),
                        "raw": {"market_name": market_name, "label": label, "league": league},
                    })
    return rows


def _get(path: str, params: Dict[str, Any]) -> Any:
    if not API_KEY:
        return None
    r = requests.get(
        f"{API_BASE}/{path.lstrip('/')}",
        params={"apiKey": API_KEY, **params},
        headers={"Accept": "application/json", "User-Agent": "PROP-HUNTER/13.9.2"},
        timeout=TIMEOUT,
    )
    if r.status_code in {401, 402, 403, 404, 429}:
        return None
    r.raise_for_status()
    return r.json()


def fetch_oddsapi_io_props(sport: str, max_events: int = MAX_EVENTS) -> List[Dict[str, Any]]:
    sport = str(sport or "").upper()
    slug = SPORT_SLUG.get(sport)
    if not API_KEY or not slug:
        return []
    events = _get("events", {"sport": slug, "status": "pending", "limit": max(1, min(max_events, MAX_EVENTS))})
    if isinstance(events, dict):
        events = events.get("data") or events.get("events") or []
    if not isinstance(events, list):
        return []
    rows: List[Dict[str, Any]] = []
    for ev in events[:max_events]:
        if not isinstance(ev, dict):
            continue
        eid = ev.get("id") or ev.get("eventId")
        if eid is None:
            continue
        params: Dict[str, Any] = {"eventId": eid}
        if BOOKMAKERS:
            params["bookmakers"] = BOOKMAKERS
        payload = _get("odds", params)
        if not isinstance(payload, dict):
            continue
        # Preserve event metadata if /odds omits it.
        merged = dict(ev)
        merged.update(payload)
        rows.extend(parse_odds_payload(merged, sport))
    return rows
