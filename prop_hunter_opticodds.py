#!/usr/bin/env python3
"""OpticOdds v3 observed player-prop adapter for PROP HUNTER.

Trial/key gated.  Uses only documented REST endpoints:
  GET /api/v3/fixtures       -> upcoming fixture ids
  GET /api/v3/fixtures/odds  -> up to 5 fixtures x 5 sportsbooks in one request

Only observed player prices are emitted.  No browser, no synthetic lines.
"""
from __future__ import annotations

import math
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

import requests

API_BASE = os.getenv("OPTICODDS_API_BASE", "https://api.opticodds.com/api/v3").rstrip("/")
API_KEY = (os.getenv("OPTICODDS_API_KEY") or os.getenv("OPTICODDS_KEY") or "").strip()
TIMEOUT = max(3, min(12, int(os.getenv("PH_OPTICODDS_TIMEOUT", "6"))))
MAX_FIXTURES = max(1, min(5, int(os.getenv("PH_OPTICODDS_MAX_FIXTURES", "5"))))
BOOKS = [x.strip() for x in os.getenv(
    "PH_OPTICODDS_BOOKS", "DraftKings,FanDuel,BetMGM,Caesars,bet365"
).split(",") if x.strip()][:5]

SUPPORTED = {"MLB", "NBA", "WNBA", "NFL", "NHL", "NCAAB", "NCAAF"}


def configured() -> bool:
    return bool(API_KEY)


def _f(value: Any) -> Optional[float]:
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def _decimal(value: Any) -> Optional[float]:
    x = _f(value)
    if x is None or x == 0:
        return None
    if 1.001 < x < 100:
        return round(x, 4)
    if x >= 100:
        return round(1 + x / 100.0, 4)
    if x <= -100:
        return round(1 + 100.0 / abs(x), 4)
    return None


def _side(odd: Dict[str, Any]) -> str:
    raw = str(odd.get("selection_line") or odd.get("side") or "").strip().lower()
    if raw in {"over", "under"}:
        return raw
    if raw == "yes":
        return "over"
    if raw == "no":
        return "under"
    text = " ".join(str(odd.get(k) or "") for k in ("name", "selection", "normalized_selection")).lower()
    if re.search(r"\b(over|higher|yes)\b", text):
        return "over"
    if re.search(r"\b(under|lower|no)\b", text):
        return "under"
    return ""


def _player(odd: Dict[str, Any]) -> str:
    # For player props OpticOdds uses selection/player_id.  Keep a defensive
    # fallback for response variants where the player is embedded in name.
    selection = str(odd.get("selection") or "").strip()
    if selection and selection.lower() not in {"over", "under", "yes", "no"}:
        return selection
    name = str(odd.get("name") or "").strip()
    cleaned = re.sub(r"\s+(?:over|under|higher|lower|yes|no)\b.*$", "", name, flags=re.I).strip(" -–—:")
    return cleaned


def _market(odd: Dict[str, Any]) -> str:
    raw = str(odd.get("market_id") or odd.get("market") or "player_prop").strip().lower()
    return re.sub(r"[^a-z0-9]+", "_", raw).strip("_") or "player_prop"


def parse_odds_payload(payload: Any, sport: str) -> List[Dict[str, Any]]:
    """Normalize /fixtures/odds response.  Testable without network access."""
    events = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(events, list):
        return []
    sport = str(sport or "").upper()
    rows: List[Dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        eid = str(event.get("id") or event.get("fixture_id") or event.get("game_id") or "")
        start = str(event.get("start_date") or event.get("commence_time") or "")
        home = str(event.get("home_team_display") or "")
        away = str(event.get("away_team_display") or "")
        if not home:
            hc = event.get("home_competitors") or []
            if hc and isinstance(hc[0], dict):
                home = str(hc[0].get("name") or "")
        if not away:
            ac = event.get("away_competitors") or []
            if ac and isinstance(ac[0], dict):
                away = str(ac[0].get("name") or "")
        league_obj = event.get("league") or {}
        league = str(league_obj.get("name") if isinstance(league_obj, dict) else league_obj or sport).upper()
        for odd in event.get("odds") or []:
            if not isinstance(odd, dict):
                continue
            # Official player props carry player_id.  This prevents game markets
            # from leaking into PROP HUNTER.
            if not odd.get("player_id"):
                continue
            direction = _side(odd)
            if direction not in {"over", "under"}:
                continue
            player = _player(odd)
            if not player:
                continue
            line = _f(odd.get("points") if odd.get("points") is not None else odd.get("line"))
            if line is None:
                raw_side = str(odd.get("selection_line") or "").lower()
                if raw_side in {"yes", "no"}:
                    line = 0.5
            if line is None:
                continue
            price = _decimal(odd.get("price"))
            if not price or not (1.001 < price <= 50):
                continue
            book = str(odd.get("sportsbook") or "opticodds").strip()
            market = _market(odd)
            rows.append({
                "source": "opticodds",
                "bookmaker": book.lower(),
                "sport": sport,
                "league": sport if sport in SUPPORTED else league,
                "source_event_id": eid,
                "event_id": eid,
                "commence_time": start,
                "home_team": home,
                "away_team": away,
                "player_name": player,
                "market": market,
                "market_key": market,
                "direction": direction,
                "line": float(line),
                "odds_decimal": float(price),
                "selection": str(odd.get("name") or odd.get("selection") or direction.title()),
                "raw": {
                    "opticodds_id": odd.get("id"),
                    "player_id": odd.get("player_id"),
                    "grouping_key": odd.get("grouping_key"),
                    "is_main": odd.get("is_main"),
                    "timestamp": odd.get("timestamp"),
                    "limits": odd.get("limits"),
                },
            })
    return rows


def _get(path: str, params: Iterable[tuple[str, Any]] | Dict[str, Any]) -> Any:
    if not API_KEY:
        return None
    try:
        r = requests.get(
            f"{API_BASE}/{path.lstrip('/')}",
            params=params,
            headers={"X-Api-Key": API_KEY, "Accept": "application/json", "User-Agent": "PROP-HUNTER/13.10"},
            timeout=TIMEOUT,
        )
        if r.status_code in {401, 402, 403, 404, 429}:
            return None
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def fetch_opticodds_props(sport: str, max_fixtures: int = MAX_FIXTURES) -> List[Dict[str, Any]]:
    sport = str(sport or "").upper()
    if not API_KEY or sport not in SUPPORTED or not BOOKS:
        return []
    max_fixtures = max(1, min(int(max_fixtures or MAX_FIXTURES), 5))
    now = datetime.now(timezone.utc)
    fixtures = _get("fixtures", {
        "league": sport,
        "status": "unplayed",
        "start_date_after": now.isoformat().replace("+00:00", "Z"),
        "start_date_before": (now + timedelta(hours=48)).isoformat().replace("+00:00", "Z"),
    })
    items = fixtures.get("data") if isinstance(fixtures, dict) else fixtures
    if not isinstance(items, list):
        return []
    ids = [str(x.get("id")) for x in items if isinstance(x, dict) and x.get("id")][:max_fixtures]
    if not ids:
        return []
    params: List[tuple[str, Any]] = []
    params.extend(("fixture_id", x) for x in ids)
    params.extend(("sportsbook", x) for x in BOOKS)
    params.append(("odds_format", "DECIMAL"))
    payload = _get("fixtures/odds", params)
    return parse_odds_payload(payload, sport)
