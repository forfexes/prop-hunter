#!/usr/bin/env python3
"""Central sanity guard for observed PROP HUNTER sportsbook rows.

Adapted from the defensive checks that proved useful in NETRATTLER, but kept
sport-agnostic. It never invents a price or line; it only rejects malformed
bookmaker rows and marks explicit binary markets as settlement-equivalent 0.5
lines.
"""
from __future__ import annotations

import math
import os
import re
from typing import Any, Dict, Optional

_GENERIC_PLAYER_RE = re.compile(
    r"^(?:over|under|higher|lower|yes|no)?\s*[+-]?\d+(?:[\.,]\d+)?(?:\s*[+]?\s*(?:points?|rebounds?|assists?|hits?|bases?|yards?|tds?|touchdowns?|goals?|shots?|saves?))?$",
    re.I,
)
_MULTI_PLAYER_TERMS = ("||", " either player", "both players", "any of ", " or ")
_BINARY_MARKET_TERMS = (
    "anytime td", "anytime touchdown", "to score a touchdown", "home run",
    "to hit a home run", "to score", "goal scorer", "goalscorer",
)


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _f(value: Any) -> Optional[float]:
    try:
        x = float(str(value).replace(",", "."))
        return x if math.isfinite(x) else None
    except Exception:
        return None


def _looks_team_or_generic(player: str, home: str = "", away: str = "") -> bool:
    p = _norm(player)
    if not p or p in {"over", "under", "higher", "lower", "yes", "no", "home", "away", "draw", "player", "total"}:
        return True
    if _GENERIC_PLAYER_RE.match(str(player or "").strip()):
        return True
    if p.startswith(("over ", "under ", "higher ", "lower ")):
        return True
    padded = f" {p} "
    if any(term in padded for term in _MULTI_PLAYER_TERMS):
        return True
    h, a = _norm(home), _norm(away)
    if p and (p == h or p == a):
        return True
    if len(p) >= 5:
        if h and (p in h or h in p) and len(p.split()) <= max(2, len(h.split())):
            return True
        if a and (p in a or a in p) and len(p.split()) <= max(2, len(a.split())):
            return True
    return False


def _binary_market(market: str, selection: str = "") -> bool:
    text = f"{_norm(market)} {_norm(selection)}"
    if any(term in text for term in _BINARY_MARKET_TERMS):
        return True
    return _norm(selection) in {"yes", "no"}


def sanitize_row(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return a safe normalized copy or None when the row is not trustworthy."""
    if not isinstance(row, dict):
        return None
    out = dict(row)
    player = str(out.get("player_name") or out.get("player") or "").strip()
    market = str(out.get("market_key") or out.get("market") or "").strip()
    home = str(out.get("home_team") or "")
    away = str(out.get("away_team") or "")
    if not player or not market or _looks_team_or_generic(player, home, away):
        return None
    price = _f(out.get("odds_decimal") if out.get("odds_decimal") is not None else out.get("odds"))
    if price is None or not (1.001 < price <= float(os.getenv("PH_MAX_DECIMAL_ODDS", "75"))):
        return None
    direction = str(out.get("direction") or "").strip().lower()
    selection = str(out.get("selection") or "").strip()
    if direction in {"yes", "higher"}:
        direction = "over"
    elif direction in {"no", "lower"}:
        direction = "under"
    if direction not in {"over", "under"}:
        text = f" {_norm(selection)} {_norm(market)} "
        if re.search(r"\b(over|higher|yes)\b", text):
            direction = "over"
        elif re.search(r"\b(under|lower|no)\b", text):
            direction = "under"
        else:
            return None
    line = _f(out.get("line") if out.get("line") is not None else out.get("point"))
    if line is None and _binary_market(market, selection):
        line = 0.5
    if line is None or line < 0:
        return None
    if line > float(os.getenv("PH_MAX_PROP_LINE", "1000")):
        return None
    out["player_name"] = player
    out["market"] = str(out.get("market") or market)
    out["market_key"] = str(out.get("market_key") or market)
    out["direction"] = direction
    out["line"] = float(line)
    out["odds_decimal"] = round(float(price), 4)
    return out


def probability_sane(probability: Any, odds_decimal: Any) -> bool:
    """Reject implausible model/market gaps that usually indicate bad matching."""
    p = _f(probability)
    odds = _f(odds_decimal)
    if p is None or odds is None or odds <= 1.001:
        return False
    if p > 1:
        p /= 100.0
    if not (0 < p < 1):
        return False
    implied = 1.0 / odds
    max_gap = float(os.getenv("PH_MAX_MODEL_MARKET_GAP", "0.35"))
    max_ratio = float(os.getenv("PH_MAX_MODEL_MARKET_RATIO", "4.0"))
    if abs(p - implied) > max_gap:
        return False
    if implied > 0 and p / implied > max_ratio:
        return False
    return True
