#!/usr/bin/env python3
"""SportsGameOdds v2 player-prop adapter for PROP HUNTER.

Fast/key-gated: no request is made unless SPORTSGAMEODDS_KEY is configured.
Uses the documented /v2/events endpoint and emits only observed bookmaker prices.
"""
from __future__ import annotations

import math
import os
from typing import Any, Dict, Iterable, List, Optional

import requests

API_BASE = os.getenv("SPORTSGAMEODDS_API_BASE", "https://api.sportsgameodds.com/v2").rstrip("/")
API_KEY = (os.getenv("SPORTSGAMEODDS_KEY") or os.getenv("SPORTS_GAME_ODDS_KEY") or "").strip()
TIMEOUT = max(3, min(12, int(os.getenv("PH_SGO_TIMEOUT", "7"))))
MAX_EVENTS = max(1, min(10, int(os.getenv("PH_SGO_MAX_EVENTS", "5"))))

LEAGUE_BY_SPORT = {
    "baseball_mlb": "MLB",
    "basketball_nba": "NBA",
    "basketball_wnba": "WNBA",
    "americanfootball_nfl": "NFL",
    "icehockey_nhl": "NHL",
    "basketball_ncaab": "NCAAB",
    "americanfootball_ncaaf": "NCAAF",
}

TEAM_ENTITIES = {"all", "home", "away", ""}


def configured() -> bool:
    return bool(API_KEY)


def _f(x: Any) -> Optional[float]:
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except Exception:
        return None


def _american_to_decimal(x: Any) -> Optional[float]:
    v = _f(x)
    if v is None or v == 0:
        return None
    return round((1 + v / 100.0) if v > 0 else (1 + 100.0 / abs(v)), 4)


def _player_name(stat_entity_id: Any) -> str:
    raw = str(stat_entity_id or "").strip()
    parts = raw.split("_")
    if len(parts) > 2:
        parts = parts[:-2]
    return " ".join(p.capitalize() for p in parts if p)


def _teams(event: Dict[str, Any]) -> tuple[str, str]:
    teams = event.get("teams") or {}
    def name(side: str) -> str:
        obj = teams.get(side) or {}
        names = obj.get("names") or {}
        return str(names.get("long") or names.get("short") or obj.get("name") or "")
    return name("home"), name("away")


def _event_start(event: Dict[str, Any]) -> str:
    status = event.get("status") or {}
    return str(status.get("startsAt") or event.get("startsAt") or event.get("commenceTime") or "")


def _market_name(odd: Dict[str, Any]) -> str:
    stat = str(odd.get("statID") or "").strip().lower()
    bet = str(odd.get("betTypeID") or "").strip().lower()
    if stat and bet and bet not in stat:
        return f"{stat}_{bet}"
    return stat or bet or str(odd.get("marketName") or odd.get("market") or "player_prop").strip().lower()


def _direction(odd: Dict[str, Any]) -> str:
    side = str(odd.get("sideID") or odd.get("side") or "").strip().lower()
    if side in {"over", "under"}:
        return side
    if side in {"yes", "no"}:
        return side
    return side or "over"


def _request_events(params: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not API_KEY:
        return []
    try:
        r = requests.get(
            f"{API_BASE}/events",
            params=params,
            headers={"x-api-key": API_KEY, "Accept": "application/json", "User-Agent": "PROP-HUNTER/13.8"},
            timeout=TIMEOUT,
        )
        if r.status_code in {401, 403, 429}:
            return []
        r.raise_for_status()
        payload = r.json()
        return list(payload.get("data") or []) if isinstance(payload, dict) else []
    except Exception:
        return []


def fetch_sgo_props(sport_key: str, max_events: int = MAX_EVENTS) -> List[Dict[str, Any]]:
    """Return normalized observed prop rows for one league.

    One league request returns event metadata plus bookmaker-level odds. This avoids
    one HTTP request per event and keeps the card runtime bounded.
    """
    league = LEAGUE_BY_SPORT.get(str(sport_key))
    if not league or not API_KEY:
        return []
    events = _request_events({
        "leagueID": league,
        "finalized": "false",
        "oddsAvailable": "true",
        "limit": max(1, min(int(max_events or MAX_EVENTS), MAX_EVENTS)),
    })
    rows: List[Dict[str, Any]] = []
    for event in events:
        event_id = str(event.get("eventID") or event.get("id") or "")
        home, away = _teams(event)
        start = _event_start(event)
        odds = event.get("odds") or {}
        if not isinstance(odds, dict):
            continue
        for odd_id, odd in odds.items():
            if not isinstance(odd, dict):
                continue
            entity = str(odd.get("statEntityID") or "").strip()
            if entity.lower() in TEAM_ENTITIES:
                continue
            player = str(odd.get("statEntityName") or odd.get("playerName") or _player_name(entity)).strip()
            if not player:
                continue
            market = _market_name(odd)
            direction = _direction(odd)
            for book, bm in (odd.get("byBookmaker") or {}).items():
                if not isinstance(bm, dict) or bm.get("available") is False:
                    continue
                line = _f(bm.get("overUnder") if bm.get("overUnder") is not None else odd.get("overUnder"))
                if line is None:
                    continue
                raw_price = bm.get("odds")
                dec = _american_to_decimal(raw_price)
                if dec is None or dec <= 1.0:
                    dec_direct = _f(bm.get("decimalOdds") or bm.get("oddsDecimal"))
                    dec = dec_direct if dec_direct and dec_direct > 1 else None
                if not dec:
                    continue
                rows.append({
                    "source": "sportsgameodds",
                    "bookmaker": str(book).lower(),
                    "sport": league,
                    "league": league,
                    "source_event_id": event_id,
                    "event_id": event_id,
                    "commence_time": start,
                    "home_team": home,
                    "away_team": away,
                    "player_name": player,
                    "market": market,
                    "market_key": market,
                    "direction": direction,
                    "line": line,
                    "odds_decimal": round(float(dec), 4),
                    "odds_american": raw_price,
                    "selection": direction.title(),
                    "raw": {"odd_id": odd_id, "stat_entity_id": entity, "last_updated": bm.get("lastUpdatedAt")},
                })
    return rows
