"""Closing Line Value tracking."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import List, Optional

import requests

from ..config import BOOKMAKERS, CLV_HISTORY_FILE, HTTP_HEADERS, ODDS_API_KEYS, ODDS_BASE, REQUEST_TIMEOUT
from ..logging_setup import get_logger

log = get_logger(__name__)


def clv_percent(opening_odds: float, closing_odds: float) -> float:
    if opening_odds <= 1 or closing_odds <= 1:
        return 0.0
    open_p = 1 / opening_odds
    close_p = 1 / closing_odds
    return round((close_p - open_p) * 100, 2)


def load_clv() -> list:
    if not os.path.exists(CLV_HISTORY_FILE):
        return []
    try:
        with open(CLV_HISTORY_FILE) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return []


def save_clv(rows: list) -> None:
    try:
        with open(CLV_HISTORY_FILE, "w") as f:
            json.dump(rows, f, indent=2, default=str)
    except OSError as e:
        log.warning("clv save: %s", e)


def record_pick_for_clv(pick: dict, event_id: str, sport: str) -> None:
    rows = load_clv()
    rows.append({
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "event_id": event_id,
        "sport": sport,
        "player": pick.get("player"),
        "market": pick.get("market"),
        "direction": pick.get("direction"),
        "point": pick.get("point"),
        "opening_odds": pick.get("odds"),
        "closing_odds": None,
        "clv_pct": None,
    })
    save_clv(rows)


def _fetch_event_odds(sport: str, event_id: str) -> Optional[dict]:
    if not ODDS_API_KEYS:
        return None
    try:
        r = requests.get(
            f"{ODDS_BASE}/sports/{sport}/events/{event_id}/odds",
            params={"apiKey": ODDS_API_KEYS[0], "regions": "us,eu",
                    "markets": "h2h", "oddsFormat": "decimal", "bookmakers": BOOKMAKERS},
            headers=HTTP_HEADERS, timeout=REQUEST_TIMEOUT,
        )
        if r.status_code == 200:
            return r.json()
    except requests.RequestException as e:
        log.warning("CLV fetch: %s", e)
    return None


def update_closing_lines(within_minutes: int = 20) -> int:
    rows = load_clv()
    updated = 0
    for row in rows:
        if row.get("closing_odds") is not None:
            continue
        data = _fetch_event_odds(row["sport"], row["event_id"])
        if not data:
            continue
        prices: List[float] = []
        for bm in data.get("bookmakers", []):
            for mkt in bm.get("markets", []):
                for o in mkt.get("outcomes", []):
                    if o.get("price"):
                        prices.append(float(o["price"]))
        if not prices:
            continue
        closing = round(sum(prices) / len(prices), 2)
        row["closing_odds"] = closing
        row["clv_pct"] = clv_percent(row["opening_odds"], closing)
        updated += 1
        time.sleep(0.2)
    if updated:
        save_clv(rows)
        log.info("CLV updated %d rows", updated)
    return updated
