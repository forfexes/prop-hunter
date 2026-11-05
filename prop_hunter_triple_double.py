"""Verified NBA triple-double market validation (no synthetic prices).

This module is deliberately independent of production publishing.
Integration requires an observed bookmaker Yes/No market and settlement mapping.
"""
from __future__ import annotations
import math
from typing import Any, Mapping


def validate_triple_double_quote(quote: Mapping[str, Any]) -> bool:
    """Accept only an explicitly observed, game-linked NBA TD Yes/No quote."""
    try:
        odds = float(quote["odds"])
        side = str(quote["selection"]).strip().lower()
        market = str(quote["market"]).strip().lower().replace("-", " ")
        sport = str(quote["sport"]).strip().upper()
        return (
            sport == "NBA"
            and "triple double" in market
            and side in {"yes", "no"}
            and math.isfinite(odds)
            and odds > 1.0
            and quote.get("odds_observed") is True
            and bool(str(quote.get("bookmaker") or "").strip())
            and bool(str(quote.get("player") or "").strip())
            and bool(str(quote.get("game_id") or "").strip())
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def is_triple_double(stats: Mapping[str, Any]) -> bool:
    """NBA: at least 10 in three of points/rebounds/assists/steals/blocks."""
    values = ("points", "rebounds", "assists", "steals", "blocks")
    try:
        return sum(float(stats.get(k, 0)) >= 10 for k in values) >= 3
    except (TypeError, ValueError, OverflowError):
        return False
