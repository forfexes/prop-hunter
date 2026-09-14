#!/usr/bin/env python3
"""PROP HUNTER market intelligence helpers.

Small dependency-free helpers used by the card runtime and tests:
- deterministic Monte-Carlo probability from player gamelogs
- bookmaker line/price movement from observed snapshots
- steam/reverse-move hints without inventing prices

The module is intentionally pure Python so it adds virtually no GitHub Actions
startup cost and can be unit-tested offline.
"""
from __future__ import annotations

import hashlib
import math
import random
from datetime import datetime, timezone
from statistics import mean, pstdev
from typing import Any, Dict, Iterable, List, Optional, Tuple


def _float(v: Any) -> Optional[float]:
    try:
        if v is None or v == "":
            return None
        x = float(v)
        if not math.isfinite(x):
            return None
        return x
    except Exception:
        return None


def _iso(v: Any) -> Optional[datetime]:
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _norm(v: Any) -> str:
    return " ".join(str(v or "").strip().lower().replace("_", " ").split())


def _direction(row: Dict[str, Any]) -> str:
    text = _norm(row.get("direction") or row.get("side") or row.get("selection") or row.get("market"))
    return "under" if "under" in text or "less" in text else "over"


def market_key(row: Dict[str, Any]) -> Tuple[str, str, str, str, str]:
    """Stable identity for one book/player/market/event side."""
    return (
        _norm(row.get("bookmaker") or row.get("book") or row.get("source")),
        _norm(row.get("source_event_id") or row.get("event_id") or row.get("game_id") or row.get("game")),
        _norm(row.get("player_name") or row.get("player")),
        _norm(row.get("market_key") or row.get("market")),
        _direction(row),
    )


def movement_index(rows: Iterable[Dict[str, Any]]) -> Dict[Tuple[str, str, str, str, str], Dict[str, Any]]:
    """Summarise observed opening/current movement per bookmaker market.

    Positive ``line_move`` means the selected side received a better line at the
    opening than at the current snapshot (i.e. the market moved toward the pick).
    Positive ``price_move_prob`` means implied probability increased.
    """
    groups: Dict[Tuple[str, str, str, str, str], List[Dict[str, Any]]] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        key = market_key(row)
        if not key[2] or not key[3]:
            continue
        groups.setdefault(key, []).append(row)

    out: Dict[Tuple[str, str, str, str, str], Dict[str, Any]] = {}
    for key, grp in groups.items():
        grp.sort(key=lambda r: _iso(r.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc))
        first, last = grp[0], grp[-1]
        open_line, cur_line = _float(first.get("line")), _float(last.get("line"))
        open_odds = _float(first.get("odds_decimal") or first.get("odds"))
        cur_odds = _float(last.get("odds_decimal") or last.get("odds"))
        side = key[-1]
        line_move = None
        if open_line is not None and cur_line is not None:
            line_move = (open_line - cur_line) if side == "under" else (cur_line - open_line)
        price_move_prob = None
        if open_odds and cur_odds and open_odds > 1 and cur_odds > 1:
            price_move_prob = (1.0 / cur_odds) - (1.0 / open_odds)
        age_min = None
        a, b = _iso(first.get("created_at")), _iso(last.get("created_at"))
        if a and b:
            age_min = max(0.0, (b - a).total_seconds() / 60.0)
        strength = 0.0
        if line_move is not None:
            strength += min(2.0, abs(line_move)) * 0.55
        if price_move_prob is not None:
            strength += min(0.08, abs(price_move_prob)) * 8.0
        steam = bool(len(grp) >= 2 and strength >= 0.35 and ((line_move or 0) > 0 or (price_move_prob or 0) > 0.012))
        out[key] = {
            "opening_line": open_line,
            "current_line": cur_line,
            "opening_odds": open_odds,
            "current_odds": cur_odds,
            "line_move": round(line_move, 4) if line_move is not None else None,
            "price_move_prob": round(price_move_prob, 6) if price_move_prob is not None else None,
            "snapshots": len(grp),
            "window_minutes": round(age_min, 1) if age_min is not None else None,
            "steam": steam,
            "movement_strength": round(strength, 4),
        }
    return out


def consensus_count(row: Dict[str, Any], rows: Iterable[Dict[str, Any]]) -> int:
    target_player = _norm(row.get("player_name") or row.get("player"))
    target_market = _norm(row.get("market_key") or row.get("market"))
    target_event = _norm(row.get("source_event_id") or row.get("event_id") or row.get("game_id") or row.get("game"))
    target_side = _direction(row)
    books = set()
    for other in rows or []:
        if _norm(other.get("player_name") or other.get("player")) != target_player:
            continue
        if _norm(other.get("market_key") or other.get("market")) != target_market:
            continue
        oe = _norm(other.get("source_event_id") or other.get("event_id") or other.get("game_id") or other.get("game"))
        if target_event and oe and target_event != oe:
            continue
        if _direction(other) != target_side:
            continue
        b = _norm(other.get("bookmaker") or other.get("book") or other.get("source"))
        if b:
            books.add(b)
    return len(books)


def monte_carlo_probability(values: Iterable[Any], line: float, direction: str = "over", simulations: int = 2000,
                            seed_key: str = "") -> Optional[float]:
    """Deterministic bootstrap Monte-Carlo probability.

    Samples historical games with recency weighting and adds a small empirical
    jitter based on observed dispersion. It is deliberately conservative: the
    final probability is shrunk toward the raw empirical hit rate.
    """
    vals = [_float(v) for v in values]
    vals = [v for v in vals if v is not None]
    if len(vals) < 6:
        return None
    try:
        line = float(line)
    except Exception:
        return None
    simulations = max(250, min(int(simulations or 2000), 10000))
    direction = "under" if str(direction).lower() == "under" else "over"
    # Newest-first input: exponential-like integer weights without numpy.
    weights = [max(1, len(vals) - i) for i in range(len(vals))]
    digest = hashlib.sha1((seed_key + repr(vals) + str(line) + direction).encode("utf-8")).hexdigest()
    rng = random.Random(int(digest[:16], 16))
    sigma = pstdev(vals) if len(vals) > 1 else 0.0
    jitter = min(max(sigma * 0.12, 0.02), max(0.15, abs(mean(vals)) * 0.08 + 0.10))
    hits = 0
    for _ in range(simulations):
        base = rng.choices(vals, weights=weights, k=1)[0]
        sim = base + rng.gauss(0.0, jitter)
        if (direction == "under" and sim < line) or (direction == "over" and sim > line):
            hits += 1
    mc = hits / simulations
    empirical = sum(1 for v in vals if ((direction == "under" and v < line) or (direction == "over" and v > line))) / len(vals)
    # Shrink simulation noise toward the directly observed rate.
    p = 0.70 * mc + 0.30 * empirical
    return round(max(0.02, min(0.98, p)), 4)
