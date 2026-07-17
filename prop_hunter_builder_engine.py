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


def _features(obj: Any) -> Dict[str, Any]:
    value = getattr(obj, "features", None)
    return value if isinstance(value, dict) else {}


def _real_price(obj: Any) -> bool:
    feats = _features(obj)
    explicit = feats.get("odds_observed")
    if explicit is not None:
        return bool(explicit)
    return str(feats.get("price_type") or "").lower() in {"bookmaker", "observed", "exchange"}


def _book(obj: Any) -> str:
    feats = _features(obj)
    return str(
        feats.get("bookmaker") or feats.get("book") or
        getattr(obj, "bookmaker", None) or ""
    ).strip().lower()


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


def _is_hr(obj: Any) -> bool:
    market = _base_market(getattr(obj, "market", ""))
    return "home run" in market or bool(re.search(r"\bhr\b", market))


def _candidate_probability(obj: Any) -> Optional[float]:
    """Return a conservative calibrated probability for a real bookmaker row."""
    odds = _odds(obj)
    if odds <= 1.01 or not _real_price(obj):
        return None

    feats = _features(obj)
    raw_prob = None
    for key in (
        "calibrated_prob", "fair_prob", "model_prob", "hit_prob",
        "proj_prob", "probability", "gamelog_fair_prob",
    ):
        value = feats.get(key)
        if value is not None:
            raw_prob = to_float(value)
            if raw_prob is not None:
                break
    if raw_prob is None:
        raw_prob = to_float(getattr(obj, "probability", None))
    if raw_prob is None:
        return None

    raw_prob = max(0.01, min(0.99, raw_prob))
    implied = max(0.01, min(0.99, 1.0 / odds))
    sample = int(to_float(feats.get("gamelog_n") or feats.get("sample_size"), 0) or 0)
    consensus = int(to_float(feats.get("consensus_sources"), 0) or 0)

    weight = min(0.68, 0.30 + sample / 80.0 + min(consensus, 4) * 0.04)
    probability = implied * (1.0 - weight) + raw_prob * weight
    probability = min(0.40 if _is_hr(obj) else 0.86, probability)
    return round(max(0.01, probability), 4)


def _candidate_key(obj: Any) -> Tuple[str, str, str, str, str]:
    point = _point(obj)
    return (
        _player(obj).lower(),
        _base_market(getattr(obj, "market", "")),
        _direction(obj),
        f"{point:g}" if point is not None else "",
        _book(obj),
    )


def _candidate_from_prop(prop: Any, PickCls: Any) -> Optional[Any]:
    """Create a positive-EV candidate only from a verified bookmaker row."""
    probability = _candidate_probability(prop)
    odds = _odds(prop)
    if probability is None or odds <= 1.01:
        return None

    edge = probability * odds - 1.0
    minimum_edge = 0.04 if _is_hr(prop) else 0.018
    if edge < minimum_edge:
        return None

    category = "hr_risk" if _is_hr(prop) else "verified_pool"
    fraction = 0.08 if _is_hr(prop) else 0.16
    cap = 0.18 if _is_hr(prop) else 0.35
    stake = _kelly(probability, odds, fraction, cap)
    if stake <= 0:
        stake = 0.05 if _is_hr(prop) else 0.10

    point = _point(prop)
    direction = _direction(prop)
    market = _base_market(getattr(prop, "market", "")).title()
    if point is not None and not _is_hr(prop):
        market = f"{market} {direction.title()} {point:g}"
    elif _is_hr(prop):
        market = "Home Run"

    features = dict(_features(prop))
    features["odds_observed"] = True
    features["price_type"] = "bookmaker"

    pick = PickCls(
        type="single",
        category=category,
        tier=1,
        player=_player(prop),
        team=getattr(prop, "team", "") or "",
        emoji=getattr(prop, "emoji", "⚾" if _is_hr(prop) else "🎯") or "🎯",
        market=market,
        direction="over" if _is_hr(prop) else direction,
        odds=round(odds, 2),
        stake=round(stake, 2),
        probability=probability,
        edge_pct=round(edge * 100.0, 1),
        ev=round(edge, 4),
        game=_game(prop),
        analysis=(
            f"Verifizierte {_book(prop)} Quote · "
            f"kalibrierte Modellprob {probability*100:.1f}%"
        ),
    )
    pick.point = point
    pick.features = features
    pick.odds_observed = True
    pick.sport = _sport(prop)
    return pick


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
    if len(set(players)) != len(players):
        return False
    keys = [(_player(x).lower(), _base_market(getattr(x, "market", "")), _direction(x)) for x in legs]
    if len(set(keys)) != len(keys):
        return False
    if not all(_odds(x) > 1 and _prob(x) > 0 and _real_price(x) for x in legs):
        return False
    # A displayed builder must be placeable at one bookmaker.
    books = {_book(x) for x in legs}
    return len(books) == 1 and "" not in books


def _real_ladder(anchor: Any, props: Iterable[Any], PickCls: Any, LadderLegCls: Any) -> Optional[Any]:
    if not _real_price(anchor):
        return None
    player = _player(anchor).lower()
    base = _base_market(getattr(anchor, "market", ""))
    direction = _direction(anchor)
    anchor_book = _book(anchor)
    if not anchor_book:
        return None

    candidates = []
    for p in props or []:
        if not _real_price(p) or _book(p) != anchor_book:
            continue
        if _player(p).lower() != player:
            continue
        if _base_market(getattr(p, "market", "")) != base:
            continue
        if _direction(p) != direction:
            continue
        point, odds = _point(p), _odds(p)
        if point is None or odds <= 1:
            continue
        candidates.append((point, odds, p))

    unique = {}
    for point, odds, p in candidates:
        # Same book + same line: keep the highest actually observed price.
        if point not in unique or odds > unique[point][0]:
            unique[point] = (odds, p)
    if len(unique) < 2:
        return None

    ordered = sorted((point, item[0], item[1]) for point, item in unique.items())
    anchor_point = _point(anchor)
    if anchor_point is None:
        return None

    if direction == "over":
        safe = max((x for x in ordered if x[0] <= anchor_point), default=ordered[0], key=lambda x: x[0])
        risk = min((x for x in ordered if x[0] > safe[0]), default=None, key=lambda x: x[0])
    else:
        safe = min((x for x in ordered if x[0] >= anchor_point), default=ordered[-1], key=lambda x: x[0])
        risk = max((x for x in ordered if x[0] < safe[0]), default=None, key=lambda x: x[0])

    if risk is None or risk[0] == safe[0]:
        return None
    # Alternate lines must have independently observed prices. Identical prices
    # are possible, but are rejected here because they commonly indicate a
    # synthetic/default-price source rather than a real alternate market.
    if abs(float(risk[1]) - float(safe[1])) < 0.005:
        return None

    safe_market = f"{base.title()} {direction.title()} {safe[0]:g}"
    risk_market = f"{base.title()} {direction.title()} {risk[0]:g}"
    return PickCls(
        type="ladder", category="ladder", player=_player(anchor),
        team=getattr(anchor, "team", "") or "", emoji=getattr(anchor, "emoji", "🎯") or "🎯",
        market=f"{base.title()} Ladder", direction=direction,
        odds=safe[1], stake=0.8, probability=_prob(anchor),
        edge_pct=getattr(anchor, "edge_pct", 0) or 0, ev=getattr(anchor, "ev", 0) or 0,
        game=_game(anchor),
        analysis=f"Echte Alt-Linien bei {anchor_book}; keine geschätzten Quoten.",
        picks=[
            LadderLegCls(market=safe_market, odds=safe[1], stake=0.6),
            LadderLegCls(market=risk_market, odds=risk[1], stake=0.2),
        ],
    )


def _make_builder(legs: Sequence[Any], label: str, PickCls: Any, pairs: Dict[str, Any]) -> Optional[Any]:
    if not _valid_combo(legs):
        return None

    odds = math.prod(_odds(x) for x in legs)
    prob, corr, corr_n = _joint_probability(legs, pairs)
    edge = prob * odds - 1.0

    thresholds = {"SAFE": 0.012, "VALUE": 0.025, "RISK": 0.045, "LOTTERY": 0.07}
    probability_floors = {"SAFE": 0.30, "VALUE": 0.16, "RISK": 0.055, "LOTTERY": 0.008}
    if edge < thresholds[label] or prob < probability_floors[label]:
        return None

    caps = {"SAFE": 0.35, "VALUE": 0.26, "RISK": 0.14, "LOTTERY": 0.06}
    fractions = {"SAFE": 0.24, "VALUE": 0.18, "RISK": 0.10, "LOTTERY": 0.04}
    stake = _kelly(prob, odds, fractions[label], caps[label])
    if stake <= 0:
        return None

    same_game = bool(_game(legs[0])) and len({_game(x) for x in legs}) == 1
    all_hr = all(_is_hr(x) for x in legs)
    category = "hr_lottery" if all_hr and label in {"RISK", "LOTTERY"} else label.lower()
    ptype = "betbuilder" if same_game and label in {"SAFE", "VALUE"} else (
        "big" if label in {"RISK", "LOTTERY"} else "kombi2"
    )

    analysis = (
        f"{'HR LOTTERY' if all_hr else label} · gemeinsame Prob {prob*100:.1f}% "
        f"· Korrelation {corr:.2f} · {_book(legs[0])}"
    )
    if corr_n:
        analysis += f" ({corr_n}+ Settlements)"

    return PickCls(
        type=ptype,
        category=category,
        player=" + ".join(_player(x) for x in legs),
        emoji="⚾" if all_hr else "🎯",
        team="",
        market=f"{len(legs)}-Leg {'HR Lottery' if all_hr else label}",
        direction="over",
        odds=round(odds, 2),
        stake=stake,
        probability=round(prob, 4),
        edge_pct=round(edge * 100, 1),
        ev=round(edge, 4),
        game=_game(legs[0]) if same_game else label,
        analysis=analysis,
        legs=[_leg_text(x) for x in legs],
    )


def build_autonomous_extras(picks: Sequence[Any], props: Iterable[Any], PickCls: Any, LadderLegCls: Any) -> List[Any]:
    """Build HR singles and all risk buckets from the complete verified pool."""
    selected = [
        p for p in picks
        if getattr(p, "type", None) == "single"
        and _prob(p) >= 0.50 and _odds(p) > 1 and _real_price(p)
    ]

    pool: List[Any] = list(selected)
    seen = {_candidate_key(p) for p in selected}

    for prop in props or []:
        candidate = _candidate_from_prop(prop, PickCls)
        if candidate is None:
            continue
        key = _candidate_key(candidate)
        if key in seen:
            continue
        seen.add(key)
        pool.append(candidate)

    if not pool:
        return []

    pool = sorted(
        pool,
        key=lambda x: ((_prob(x) * _odds(x) - 1.0), _prob(x)),
        reverse=True,
    )[:28]

    corr = safe_json_load(CORR_FILE, {}) or {}
    pairs = corr.get("pairs", {}) if isinstance(corr, dict) else {}
    extras: List[Any] = []

    # Dedicated verified Home Run lane.
    selected_keys = {_candidate_key(p) for p in selected}
    hr_candidates = [
        p for p in pool
        if _is_hr(p) and _candidate_key(p) not in selected_keys
    ]
    hr_candidates.sort(
        key=lambda p: ((getattr(p, "ev", 0) or 0), _prob(p)),
        reverse=True,
    )
    extras.extend(hr_candidates[:3])

    # One genuine same-book alternate-line ladder.
    for anchor in pool:
        ladder = _real_ladder(anchor, props, PickCls, LadderLegCls)
        if ladder:
            extras.append(ladder)
            break

    candidates: Dict[str, List[Any]] = {
        "SAFE": [], "VALUE": [], "RISK": [], "LOTTERY": []
    }

    by_book: Dict[str, List[Any]] = {}
    for candidate in pool:
        book = _book(candidate)
        if book:
            by_book.setdefault(book, []).append(candidate)

    for book_pool in by_book.values():
        book_pool = sorted(
            book_pool,
            key=lambda x: ((_prob(x) * _odds(x) - 1.0), _prob(x)),
            reverse=True,
        )[:14]

        for size in (2, 3, 4):
            for legs in itertools.combinations(book_pool, size):
                odds = math.prod(_odds(x) for x in legs)
                min_prob = min(_prob(x) for x in legs)
                all_hr = all(_is_hr(x) for x in legs)

                if all_hr:
                    label = "RISK" if size == 2 and odds < 25 else "LOTTERY"
                elif size == 2:
                    if min_prob >= 0.60 and odds <= 4.5:
                        label = "SAFE"
                    elif odds <= 7.5:
                        label = "VALUE"
                    else:
                        label = "RISK"
                elif size == 3:
                    if min_prob >= 0.52 and odds <= 9.0:
                        label = "VALUE"
                    elif odds <= 22.0:
                        label = "RISK"
                    else:
                        label = "LOTTERY"
                else:
                    label = "LOTTERY"

                built = _make_builder(legs, label, PickCls, pairs)
                if built:
                    candidates[label].append(built)

    for label in ("SAFE", "VALUE", "RISK", "LOTTERY"):
        if candidates[label]:
            candidates[label].sort(
                key=lambda p: (
                    getattr(p, "ev", 0) or 0,
                    getattr(p, "probability", 0) or 0,
                ),
                reverse=True,
            )
            extras.append(candidates[label][0])

    # Preserve one dedicated HR lottery in addition to the general buckets.
    hr_tickets = [
        item for item in candidates["RISK"] + candidates["LOTTERY"]
        if getattr(item, "category", "") == "hr_lottery"
    ]
    if hr_tickets:
        hr_tickets.sort(
            key=lambda p: (
                getattr(p, "ev", 0) or 0,
                getattr(p, "probability", 0) or 0,
            ),
            reverse=True,
        )
        best_hr = hr_tickets[0]
        signature = tuple(getattr(best_hr, "legs", []) or [])
        if not any(
            tuple(getattr(existing, "legs", []) or []) == signature
            for existing in extras
        ):
            extras.append(best_hr)

    return extras

