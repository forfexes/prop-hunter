#!/usr/bin/env python3
"""Real-line autonomous ladder and builder engine.

Unlike the former fallback, this engine never invents alternate lines or odds.
Ladders are built only from independently observed source rows. Builders use the
learned empirical pair factors and require positive joint EV.
"""
from __future__ import annotations

import itertools
import math
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from prop_hunter_builder_learning import market_group, pair_key
from prop_hunter_shared_utils import safe_json_load, to_float

CORR_FILE = "prop_hunter_builder_correlations.json"


def _prob(p: Any) -> float:
    value = to_float(getattr(p, "probability", None), 0.0) or 0.0
    return max(0.01, min(0.99, value))


def _odds(p: Any) -> float:
    return to_float(getattr(p, "odds", None), 0.0) or 0.0


def _point(obj: Any) -> Optional[float]:
    value = getattr(obj, "point", None)
    if value is None: value = getattr(obj, "line", None)
    return to_float(value)


def _direction(obj: Any) -> str:
    explicit = getattr(obj, "direction", None)
    if explicit: return str(explicit).lower()
    return "under" if "under" in str(getattr(obj, "market", "")).lower() else "over"


def _base_market(text: Any) -> str:
    s = str(text or "").lower()
    s = re.sub(r"\b(over|under|more|less|yes|no)\b", " ", s)
    s = re.sub(r"\b\d+(?:\.\d+)?\b", " ", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _player(obj: Any) -> str:
    return str(getattr(obj, "player", None) or getattr(obj, "player_name", None) or "").strip()


def _game(obj: Any) -> str:
    return str(getattr(obj, "game", None) or getattr(obj, "game_id", None) or getattr(obj, "source_event_id", None) or "").strip()


def _sport(obj: Any) -> str:
    return str(getattr(obj, "sport", None) or getattr(obj, "league", None) or "UNKNOWN").upper()


def _leg_text(p: Any) -> str:
    line = _point(p)
    direction = _direction(p).title()
    market = _base_market(getattr(p, "market", "")).title()
    suffix = f" {direction} {line:g}" if line is not None else ""
    return f"{_player(p)} {market}{suffix} @{_odds(p):.2f}".strip()


def _kelly(prob: float, odds: float, fraction: float, cap: float) -> float:
    if odds <= 1: return 0.0
    full = (prob * odds - 1) / (odds - 1)
    return round(max(0.0, min(cap, full * fraction)), 2)


def _pair_factor(a: Any, b: Any, pairs: Dict[str, Any]) -> Tuple[float, int]:
    sport = _sport(a) if _sport(a) != "UNKNOWN" else _sport(b)
    ka = f"{sport}:{market_group(getattr(a, 'market', ''))}:{_direction(a)}"
    kb = f"{sport}:{market_group(getattr(b, 'market', ''))}:{_direction(b)}"
    info = pairs.get(pair_key(ka, kb)) or {}
    return float(info.get("factor", 1.0)), int(info.get("n", 0))


def _joint_probability(legs: Sequence[Any], pairs: Dict[str, Any]) -> Tuple[float, float, int]:
    independent = math.prod(_prob(x) for x in legs)
    factors, samples = [], []
    for a, b in itertools.combinations(legs, 2):
        factor, n = _pair_factor(a, b, pairs)
        factors.append(factor); samples.append(n)
    corr = math.prod(factors) ** (1 / len(factors)) if factors else 1.0
    # Conservative: learned positive correlation receives only half weight.
    adjusted = independent * (1.0 + (corr - 1.0) * 0.5)
    return max(0.002, min(0.97, adjusted)), corr, min(samples) if samples else 0


def _valid_combo(legs: Sequence[Any]) -> bool:
    players = [_player(x).lower() for x in legs]
    if len(set(players)) != len(players): return False
    # Avoid conflicting opposite sides of the same market and player.
    keys = [(_player(x).lower(), _base_market(getattr(x, "market", "")), _direction(x)) for x in legs]
    if len(set(keys)) != len(keys): return False
    return all(_odds(x) > 1 and _prob(x) > 0 for x in legs)


def _real_ladder(anchor: Any, props: Iterable[Any], PickCls: Any, LadderLegCls: Any) -> Optional[Any]:
    player = _player(anchor).lower(); base = _base_market(getattr(anchor, "market", "")); direction = _direction(anchor)
    candidates = []
    for p in props or []:
        if _player(p).lower() != player: continue
        if _base_market(getattr(p, "market", "")) != base: continue
        if _direction(p) != direction: continue
        point, odds = _point(p), _odds(p)
        if point is None or odds <= 1: continue
        candidates.append((point, odds, p))
    unique = {}
    for point, odds, p in candidates:
        # Prefer rows with real sportsbook odds over pick'em rows without odds.
        if point not in unique or odds > unique[point][0]: unique[point] = (odds, p)
    if len(unique) < 2: return None
    ordered = sorted((point, odds_p[0], odds_p[1]) for point, odds_p in unique.items())
    anchor_point = _point(anchor)
    if anchor_point is None: return None
    if direction == "over":
        safe = max((x for x in ordered if x[0] <= anchor_point), default=ordered[0], key=lambda x: x[0])
        risk = min((x for x in ordered if x[0] > safe[0]), default=None, key=lambda x: x[0])
    else:
        safe = min((x for x in ordered if x[0] >= anchor_point), default=ordered[-1], key=lambda x: x[0])
        risk = max((x for x in ordered if x[0] < safe[0]), default=None, key=lambda x: x[0])
    if risk is None or risk[0] == safe[0]: return None
    safe_market = f"{base.title()} {direction.title()} {safe[0]:g}"
    risk_market = f"{base.title()} {direction.title()} {risk[0]:g}"
    return PickCls(
        type="ladder", category="ladder", player=_player(anchor), team=getattr(anchor, "team", "") or "",
        emoji=getattr(anchor, "emoji", "🎯") or "🎯", market=f"{base.title()} Ladder", direction=direction,
        odds=safe[1], stake=0.8, probability=_prob(anchor), edge_pct=getattr(anchor, "edge_pct", 0) or 0,
        ev=getattr(anchor, "ev", 0) or 0, game=_game(anchor),
        analysis="Nur echte verfügbare Alt-Linien; keine geschätzten Ladder-Quoten.",
        picks=[LadderLegCls(market=safe_market, odds=safe[1], stake=0.6), LadderLegCls(market=risk_market, odds=risk[1], stake=0.2)],
    )


def _make_builder(legs: Sequence[Any], label: str, PickCls: Any, pairs: Dict[str, Any]) -> Optional[Any]:
    if not _valid_combo(legs): return None
    odds = math.prod(_odds(x) for x in legs)
    prob, corr, corr_n = _joint_probability(legs, pairs)
    edge = prob * odds - 1.0
    thresholds = {"SAFE": 0.015, "VALUE": 0.035, "RISK": 0.07, "LOTTERY": 0.10}
    if edge < thresholds[label]: return None
    caps = {"SAFE": 0.35, "VALUE": 0.28, "RISK": 0.16, "LOTTERY": 0.08}
    fractions = {"SAFE": 0.25, "VALUE": 0.20, "RISK": 0.12, "LOTTERY": 0.06}
    stake = _kelly(prob, odds, fractions[label], caps[label])
    if stake <= 0: return None
    same_game = bool(_game(legs[0])) and len({_game(x) for x in legs}) == 1
    ptype = "betbuilder" if same_game else ("big" if label in {"RISK", "LOTTERY"} else "kombi2")
    analysis = f"{label} · gemeinsame Prob {prob*100:.1f}% · Korrelation {corr:.2f}"
    if corr_n: analysis += f" ({corr_n}+ Settlements)"
    return PickCls(
        type=ptype, category=label.lower(), player=" + ".join(_player(x) for x in legs),
        emoji="🎯", team="", market=f"{len(legs)}-Leg {label}", direction="over",
        odds=round(odds, 2), stake=stake, probability=round(prob, 4),
        edge_pct=round(edge * 100, 1), ev=round(edge, 4), game=_game(legs[0]) if same_game else label,
        analysis=analysis, legs=[_leg_text(x) for x in legs],
    )


def build_autonomous_extras(picks: Sequence[Any], props: Iterable[Any], PickCls: Any, LadderLegCls: Any) -> List[Any]:
    singles = [p for p in picks if getattr(p, "type", None) == "single" and _prob(p) >= 0.50 and _odds(p) > 1]
    if not singles: return []
    singles = sorted(singles, key=lambda x: ((_prob(x) * _odds(x) - 1), _prob(x)), reverse=True)[:16]
    corr = safe_json_load(CORR_FILE, {}) or {}; pairs = corr.get("pairs", {}) if isinstance(corr, dict) else {}
    extras: List[Any] = []

    # One real ladder from the strongest eligible single.
    for anchor in singles:
        ladder = _real_ladder(anchor, props, PickCls, LadderLegCls)
        if ladder:
            extras.append(ladder); break

    candidates: Dict[str, List[Any]] = {"SAFE": [], "VALUE": [], "RISK": [], "LOTTERY": []}
    for size in (2, 3, 4):
        for legs in itertools.combinations(singles, size):
            odds = math.prod(_odds(x) for x in legs)
            min_prob = min(_prob(x) for x in legs)
            if size == 2 and min_prob >= 0.58 and odds <= 5.0: label = "SAFE"
            elif size <= 3 and min_prob >= 0.52 and odds <= 8.0: label = "VALUE"
            elif size >= 3 and odds < 12.0: label = "RISK"
            else: label = "LOTTERY"
            built = _make_builder(legs, label, PickCls, pairs)
            if built: candidates[label].append(built)
    # Rank by EV, then calibrated joint probability. One per risk bucket avoids spam.
    for label in ("SAFE", "VALUE", "RISK", "LOTTERY"):
        if candidates[label]:
            candidates[label].sort(key=lambda p: (getattr(p, "ev", 0) or 0, getattr(p, "probability", 0) or 0), reverse=True)
            extras.append(candidates[label][0])
    return extras
