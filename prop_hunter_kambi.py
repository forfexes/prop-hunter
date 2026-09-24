#!/usr/bin/env python3
"""Best-effort Kambi public offering adapter for PROP HUNTER.

Derived from the working NETRATTLER Kambi strategy. It is intentionally optional:
no API key is required, but geo/brand availability can vary. Only observed Kambi
prices are emitted; failures are soft and never trigger a browser.
"""
from __future__ import annotations

import math
import os
import re
from typing import Any, Dict, List, Optional

import requests

ENABLED = str(os.getenv("PH_KAMBI_ENABLED", "0")).lower() in {"1", "true", "yes", "on"}
TIMEOUT = max(3, min(10, int(os.getenv("PH_KAMBI_TIMEOUT", "5"))))
BRANDS = [x.strip() for x in os.getenv("PH_KAMBI_BRANDS", "ub,bs,888,nb").split(",") if x.strip()]
HOSTS = ["https://eu-offering-api.kambicdn.com", "https://e0-api.kambi.com"]
SPORT_PATHS = {
    "MLB": ("baseball",),
    "NBA": ("basketball",),
    "WNBA": ("basketball",),
    "NFL": ("american_football", "american-football"),
    "NHL": ("ice_hockey", "ice-hockey"),
    "NCAAB": ("basketball",),
    "NCAAF": ("american_football", "american-football"),
}


def configured() -> bool:
    return ENABLED


def _f(x: Any) -> Optional[float]:
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except Exception:
        return None


def _decimal_price(outcome: Dict[str, Any]) -> Optional[float]:
    # Kambi often exposes odds as milli-odds (e.g. 1850 => 1.85).
    for key in ("oddsDecimal", "decimalOdds"):
        v = _f(outcome.get(key))
        if v and v > 1:
            return v
    v = _f(outcome.get("odds"))
    if v and v > 100:
        return round(v / 1000.0, 4)
    if v and 1 < v < 100:
        return v
    return None


def _get(url: str, params=None) -> Any:
    try:
        r = requests.get(url, params=params or {}, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0 PROP-HUNTER"}, timeout=TIMEOUT)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


def _norm_market(label: str) -> str:
    s = str(label or "").lower()
    s = re.sub(r"\b(over|under|yes|no)\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s or "player_prop"


def _looks_player_prop(offer: Dict[str, Any], outcome: Dict[str, Any]) -> bool:
    label = " ".join([
        str((offer.get("criterion") or {}).get("label") or ""),
        str(offer.get("betOfferType", {}).get("name") or ""),
        str(outcome.get("label") or outcome.get("participant") or ""),
    ]).lower()
    tokens = ("player", "points", "rebounds", "assists", "yards", "touchdown", "strikeouts", "home run", "hits", "shots", "saves", "goals")
    return any(t in label for t in tokens)


def _player_from(offer: Dict[str, Any], outcome: Dict[str, Any]) -> str:
    for key in ("participant", "participantName", "playerName"):
        if outcome.get(key):
            return str(outcome.get(key)).strip()
    label = str(outcome.get("label") or "").strip()
    crit = str((offer.get("criterion") or {}).get("label") or "").strip()
    # Common shape: "LeBron James - Over 25.5".
    if " - " in label:
        head = label.split(" - ", 1)[0].strip()
        if head and head.lower() not in {"over", "under", "yes", "no"}:
            return head
    # Criterion may include player name before a colon/dash.
    for sep in (" - ", ": "):
        if sep in crit:
            head = crit.split(sep, 1)[0].strip()
            if head and len(head.split()) >= 2:
                return head
    return ""


def parse_offer(offer_payload: Any, sport: str, event_id: str, home: str, away: str, start: str, brand: str) -> List[Dict[str, Any]]:
    offers = offer_payload.get("betOffers") if isinstance(offer_payload, dict) else offer_payload
    if not isinstance(offers, list):
        return []
    rows: List[Dict[str, Any]] = []
    for offer in offers:
        if not isinstance(offer, dict):
            continue
        crit = str((offer.get("criterion") or {}).get("label") or offer.get("label") or "")
        for outcome in offer.get("outcomes") or []:
            if not isinstance(outcome, dict) or not _looks_player_prop(offer, outcome):
                continue
            player = _player_from(offer, outcome)
            if not player:
                continue
            label = str(outcome.get("label") or "")
            low = label.lower()
            direction = "under" if "under" in low else "over" if "over" in low else "under" if "no" == low.strip() else "over"
            line = _f(outcome.get("line") or outcome.get("points") or outcome.get("handicap"))
            if line is None:
                m = re.search(r"(\d+(?:\.\d+)?)", label + " " + crit)
                line = float(m.group(1)) if m else 0.5
            price = _decimal_price(outcome)
            if not price or price <= 1:
                continue
            rows.append({
                "source": "kambi",
                "bookmaker": f"kambi_{brand}",
                "sport": sport,
                "league": sport,
                "source_event_id": event_id,
                "event_id": event_id,
                "commence_time": start,
                "home_team": home,
                "away_team": away,
                "player_name": player,
                "market": _norm_market(crit),
                "market_key": _norm_market(crit),
                "direction": direction,
                "line": line,
                "odds_decimal": round(float(price), 4),
                "selection": label,
                "raw": {"criterion": crit, "outcome_id": outcome.get("id"), "brand": brand},
            })
    return rows


def fetch_kambi_props(sport: str, max_events: int = 3) -> List[Dict[str, Any]]:
    sport = str(sport or "").upper()
    if not ENABLED or sport not in SPORT_PATHS:
        return []
    rows: List[Dict[str, Any]] = []
    for brand in BRANDS[:2]:
        for host in HOSTS:
            events = None
            for sport_path in SPORT_PATHS[sport]:
                events = _get(
                    f"{host}/offering/v2018/{brand}/listView/{sport_path}/all/all/all/matches.json",
                    {"lang": "en_GB", "market": "GB"},
                )
                if isinstance(events, dict) and events.get("events"):
                    break
            if not isinstance(events, dict):
                continue
            count = 0
            for wrapper in events.get("events") or []:
                e = wrapper.get("event") if isinstance(wrapper, dict) else None
                e = e or wrapper
                if not isinstance(e, dict):
                    continue
                # Filter college/pro leagues conservatively using event/league text.
                text = " ".join(str(e.get(k) or "") for k in ("name", "englishName", "pathName", "group"))
                t = text.lower()
                if sport == "NBA" and "wnba" in t:
                    continue
                if sport == "WNBA" and "wnba" not in t:
                    continue
                if sport == "NFL" and "nfl" not in t:
                    continue
                if sport == "NCAAF" and not any(x in t for x in ("ncaa", "college")):
                    continue
                if sport == "NCAAB" and not any(x in t for x in ("ncaa", "college")):
                    continue
                eid = e.get("id")
                if not eid:
                    continue
                offer = _get(f"{host}/offering/v2018/{brand}/betoffer/event/{eid}.json", {"lang": "en_GB", "market": "GB"})
                home = str(e.get("homeName") or "")
                away = str(e.get("awayName") or "")
                start = str(e.get("start") or e.get("startTime") or "")
                parsed = parse_offer(offer, sport, str(eid), home, away, start, brand)
                if parsed:
                    rows.extend(parsed)
                count += 1
                if count >= max_events:
                    break
            if rows:
                return rows
    return rows
