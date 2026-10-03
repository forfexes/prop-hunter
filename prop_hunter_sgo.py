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
API_KEY = (os.getenv("SPORTSGAMEODDS_KEY") or os.getenv("SPORTSGAMEODDS_API_KEY") or os.getenv("SPORTS_GAME_ODDS_KEY") or "").strip()
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
    "icehockey_ahl": "AHL",
    "icehockey_shl": "SHL",
    "basketball_g_league": "NBA_G_LEAGUE",
    "americanfootball_cfl": "CFL",
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
    """Best-effort player label from v2 IDs such as LEBRON_JAMES_1_NBA.

    SportsGameOdds v2 player IDs may include a numeric disambiguator before the
    league suffix.  Neither the league token nor that numeric ID belongs in the
    display name.
    """
    raw = str(stat_entity_id or "").strip()
    parts = [p for p in raw.split("_") if p]
    if parts and parts[-1].upper() in {"NBA","WNBA","MLB","NFL","NHL","NCAAB","NCAAF","AHL","SHL","CFL","G","LEAGUE"}:
        parts = parts[:-1]
    if parts and parts[-1].isdigit():
        parts = parts[:-1]
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
    return str(
        status.get("startsAt")
        or event.get("startTime")
        or event.get("startsAt")
        or event.get("commenceTime")
        or ""
    )


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
            headers={"x-api-key": API_KEY, "Accept": "application/json", "User-Agent": "PROP-HUNTER/13.9.2"},
            timeout=TIMEOUT,
        )
        if r.status_code in {401, 403, 429}:
            return []
        r.raise_for_status()
        payload = r.json()
        return list(payload.get("data") or []) if isinstance(payload, dict) else []
    except Exception:
        return []


def parse_events(events: Iterable[Dict[str, Any]], league: str) -> List[Dict[str, Any]]:
    """Normalize SportsGameOdds event payloads without network access.

    Kept separate from the HTTP function so the production parser can be fixture-
    tested in the runtime guard before every GitHub card run.
    """
    rows: List[Dict[str, Any]] = []
    for event in events or []:
        if not isinstance(event, dict):
            continue
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
            # Prefer the canonical Event.players display name when present.
            players = event.get("players") or {}
            pobj = players.get(entity) if isinstance(players, dict) else None
            pnames = (pobj or {}).get("names") if isinstance(pobj, dict) else {}
            player = str(
                odd.get("statEntityName")
                or odd.get("playerName")
                or ((pnames or {}).get("display") if isinstance(pnames, dict) else "")
                or ((pobj or {}).get("name") if isinstance(pobj, dict) else "")
                or _player_name(entity)
            ).strip()
            if not player:
                continue
            market = _market_name(odd)
            direction = _direction(odd)
            seen_quotes = set()
            for book, bm in (odd.get("byBookmaker") or {}).items():
                if not isinstance(bm, dict):
                    continue
                # V2 puts alternate lines inside each bookmaker entry.  Process the
                # main quote and every observed alt line; never synthesize a rung.
                quotes = [(False, bm)]
                for alt in bm.get("altLines") or []:
                    if isinstance(alt, dict):
                        quotes.append((True, alt))
                for is_alt, quote in quotes:
                    if quote.get("available", bm.get("available", True)) is False:
                        continue
                    line = _f(
                        quote.get("overUnder")
                        if quote.get("overUnder") is not None
                        else bm.get("overUnder")
                        if bm.get("overUnder") is not None
                        else odd.get("overUnder")
                    )
                    if line is None and direction in {"yes", "no"}:
                        line = 0.5
                    if line is None:
                        continue
                    raw_price = quote.get("odds")
                    dec = _american_to_decimal(raw_price)
                    if dec is None or dec <= 1.0:
                        dec_direct = _f(quote.get("decimalOdds") or quote.get("oddsDecimal"))
                        dec = dec_direct if dec_direct and dec_direct > 1 else None
                    if not dec:
                        continue
                    quote_key = (str(book).lower(), direction, float(line), round(float(dec), 4))
                    if quote_key in seen_quotes:
                        continue
                    seen_quotes.add(quote_key)
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
                        "created_at": quote.get("lastUpdatedAt") or bm.get("lastUpdatedAt"),
                        "raw": {
                            "odd_id": odd_id, "stat_entity_id": entity,
                            "last_updated": quote.get("lastUpdatedAt") or bm.get("lastUpdatedAt"),
                            "alt_line": bool(is_alt),
                            "score": odd.get("score"),
                            "scoring_supported": odd.get("scoringSupported"),
                            "event_ended": (event.get("status") or {}).get("ended"),
                            "event_finalized": (event.get("status") or {}).get("finalized"),
                            "event_cancelled": event.get("cancelled"),
                        },
                    })
    return rows


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
        "oddsAvailable": "true",
        "includeAltLines": "true",
        "limit": max(1, min(int(max_events or MAX_EVENTS), MAX_EVENTS)),
    })
    return parse_events(events, league)
