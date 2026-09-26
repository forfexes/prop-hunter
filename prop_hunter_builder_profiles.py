#!/usr/bin/env python3
"""Expanded real-line Same Game Builder profiles for PROP HUNTER.

This module augments the existing ladder/builder engine without inventing prop
lines. It is designed from observed sportsbook-style cards: conservative
alternate-line SGPs, normal value builders, aggressive builders, same-player
multi-stat specials and longshots. Legs always come from observed bookmaker
rows that independently pass the existing positive-EV candidate guard.

The combined SGP price is still an estimate when a book does not expose a
quoted parlay price. That fact is carried in ``features`` and the analysis text
so it can never be confused with an observed single-leg quote.
"""
from __future__ import annotations

import itertools
import math
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import prop_hunter_builder_engine as base

PROFILE_BANDS = {
    "SAFE": (1.65, 2.35),
    "VALUE": (2.35, 5.50),
    "AGGRESSIVE": (5.50, 20.0),
    "LONGSHOT": (20.0, 250.0),
}
PROFILE_EDGE = {"SAFE": 0.015, "VALUE": 0.025, "AGGRESSIVE": 0.045, "LONGSHOT": 0.070}
PROFILE_PROB = {"SAFE": 0.30, "VALUE": 0.13, "AGGRESSIVE": 0.035, "LONGSHOT": 0.004}
PROFILE_MIN_LEG_PROB = {"SAFE": 0.62, "VALUE": 0.50, "AGGRESSIVE": 0.34, "LONGSHOT": 0.18}
PROFILE_MAX_LEGS = {"SAFE": 6, "VALUE": 8, "AGGRESSIVE": 10, "LONGSHOT": 10}
PROFILE_FRACTION = {"SAFE": 0.20, "VALUE": 0.14, "AGGRESSIVE": 0.07, "LONGSHOT": 0.025}
PROFILE_CAP = {"SAFE": 0.60, "VALUE": 0.35, "AGGRESSIVE": 0.15, "LONGSHOT": 0.06}
PROFILE_FLOOR = {"SAFE": 0.25, "VALUE": 0.15, "AGGRESSIVE": 0.08, "LONGSHOT": 0.05}


def _signature(legs: Sequence[Any]) -> Tuple[Tuple[str, str, str, str], ...]:
    sig = []
    for x in legs:
        sig.append((
            base._player(x).lower(),
            base._base_market(getattr(x, "market", "")),
            base._direction(x),
            f"{base._point(x):g}" if base._point(x) is not None else "",
        ))
    return tuple(sorted(sig))


def _profile_for_odds(odds: float) -> Optional[str]:
    for name, (lo, hi) in PROFILE_BANDS.items():
        if lo <= odds < hi or (name == "LONGSHOT" and math.isclose(odds, hi)):
            return name
    return None


def _market_family(obj: Any) -> str:
    m = base._base_market(getattr(obj, "market", ""))
    aliases = {
        "three pointers": "threes",
        "3 pointers": "threes",
        "3pm": "threes",
        "passing tds": "passing touchdowns",
        "pass tds": "passing touchdowns",
        "anytime touchdown scorer": "touchdowns",
        "anytime td": "touchdowns",
    }
    return aliases.get(m, m)


def _compatible(legs: Sequence[Any], nxt: Any) -> bool:
    """Allow same-player multi-stat legs, but never duplicate the same stat."""
    if not base._real_price(nxt) or base._odds(nxt) <= 1.01 or base._prob(nxt) <= 0:
        return False
    if not legs:
        return True
    if base._book(nxt) != base._book(legs[0]) or base._game(nxt) != base._game(legs[0]):
        return False

    np = base._player(nxt).lower()
    nm = _market_family(nxt)
    same_player_count = 0
    for old in legs:
        op = base._player(old).lower()
        om = _market_family(old)
        if op == np:
            same_player_count += 1
            # Same stat on the same player is a ladder, not a builder leg pair.
            if om == nm:
                return False
    # Same-player specials stay focused: at most three distinct stat families/player.
    return same_player_count < 3


def _joint_probability(legs: Sequence[Any], pairs: Dict[str, Any]) -> Tuple[float, float, int]:
    """Conservative joint probability with learned pair factors and penalties."""
    independent = math.prod(base._prob(x) for x in legs)
    factor_product = 1.0
    samples: List[int] = []
    pair_count = 0
    for a, b in itertools.combinations(legs, 2):
        factor, n = base._pair_factor(a, b, pairs)
        samples.append(n)
        pair_count += 1
        # No positive boost without real settlement history. Negative factors are
        # allowed immediately because they are conservative.
        if n >= 20:
            used = max(0.78, min(1.12, float(factor)))
            used = 1.0 + (used - 1.0) * 0.45
        else:
            used = min(1.0, max(0.86, float(factor)))
        if base._player(a).lower() == base._player(b).lower():
            used *= 0.91
        factor_product *= used
    corr = factor_product ** (1.0 / pair_count) if pair_count else 1.0
    adjusted = min(min(base._prob(x) for x in legs), independent * factor_product)
    return max(0.001, min(0.96, adjusted)), corr, min(samples) if samples else 0


def _candidate_pool(picks: Sequence[Any], props: Iterable[Any], PickCls: Any) -> List[Any]:
    pool: List[Any] = []
    seen = set()
    for p in picks or []:
        if getattr(p, "type", None) != "single" or not base._real_price(p):
            continue
        key = base._candidate_key(p)
        if key not in seen and base._prob(p) > 0 and base._odds(p) > 1.01:
            seen.add(key)
            pool.append(p)
    for prop in props or []:
        c = base._candidate_from_prop(prop, PickCls)
        if c is None:
            continue
        key = base._candidate_key(c)
        if key in seen:
            continue
        seen.add(key)
        pool.append(c)
    return pool


def _make_profile_builder(legs: Sequence[Any], profile: str, PickCls: Any, pairs: Dict[str, Any]) -> Optional[Any]:
    odds = math.prod(base._odds(x) for x in legs)
    if _profile_for_odds(odds) != profile:
        return None
    if len(legs) > PROFILE_MAX_LEGS[profile]:
        return None
    if min(base._prob(x) for x in legs) < PROFILE_MIN_LEG_PROB[profile]:
        return None

    prob, corr, corr_n = _joint_probability(legs, pairs)
    edge = prob * odds - 1.0
    if prob < PROFILE_PROB[profile] or edge < PROFILE_EDGE[profile]:
        return None

    stake = base._kelly(prob, odds, PROFILE_FRACTION[profile], PROFILE_CAP[profile])
    stake = max(PROFILE_FLOOR[profile], min(PROFILE_CAP[profile], stake))
    same_player = any(v > 1 for v in Counter(base._player(x).lower() for x in legs).values())
    book = base._book(legs[0])
    game = base._game(legs[0])
    label = {
        "SAFE": "SAFE SGP",
        "VALUE": "VALUE SGP",
        "AGGRESSIVE": "AGGRESSIVE SGP",
        "LONGSHOT": "LONGSHOT SGP",
    }[profile]
    analysis = (
        f"{label} · {len(legs)} echte +EV Legs · gemeinsame Prob {prob*100:.1f}% "
        f"· Korrelation {corr:.2f} · {book}"
    )
    if same_player:
        analysis += " · Same-Player Multi-Stat"
    if corr_n:
        analysis += f" · Pair-History {corr_n}+"
    analysis += " · Kombiquote aus beobachteten Leg-Quoten; finale SGP-Quote beim Book prüfen"

    built = PickCls(
        type="betbuilder",
        category=f"builder_{profile.lower()}",
        tier=1 if profile in {"SAFE", "VALUE"} else 2,
        player=" + ".join(dict.fromkeys(base._player(x) for x in legs)),
        team="",
        emoji=getattr(legs[0], "emoji", None) or "🎯",
        market=f"{len(legs)}-Leg {label}",
        direction="over",
        odds=round(odds, 2),
        stake=round(stake, 2),
        probability=round(prob, 4),
        edge_pct=round(edge * 100.0, 1),
        ev=round(edge, 4),
        game=game,
        analysis=analysis,
        legs=[base._leg_text(x) for x in legs],
    )
    built.sport = base._sport(legs[0])
    built.leg_details = [{
        "player": base._player(x),
        "sport": base._sport(x),
        "market": getattr(x, "market", ""),
        "market_family": _market_family(x),
        "direction": base._direction(x),
        "point": base._point(x),
        "odds": base._odds(x),
        "probability": base._prob(x),
        "bookmaker": base._book(x),
        "game": base._game(x),
    } for x in legs]
    built.features = {
        "odds_observed": False,
        "price_type": "derived_builder",
        "bookmaker": book,
        "builder_profile": profile.lower(),
        "leg_count": len(legs),
        "same_player_multistat": same_player,
        "builder_odds_estimated_from_legs": True,
    }
    return built


def _beam_build(group: Sequence[Any], PickCls: Any, pairs: Dict[str, Any], max_legs: int = 10) -> List[Any]:
    """Bounded combination search; avoids C(n,10) explosion on large slates."""
    ranked = sorted(
        group,
        key=lambda x: ((base._prob(x) * base._odds(x) - 1.0), base._prob(x)),
        reverse=True,
    )[:20]
    beams: List[Tuple[int, ...]] = [(i,) for i in range(len(ranked))]
    out: List[Any] = []
    seen_signatures = set()

    for size in range(2, max_legs + 1):
        expanded: List[Tuple[float, Tuple[int, ...]]] = []
        for idxs in beams:
            start = idxs[-1] + 1
            legs0 = [ranked[i] for i in idxs]
            for j in range(start, len(ranked)):
                nxt = ranked[j]
                if not _compatible(legs0, nxt):
                    continue
                new_idxs = idxs + (j,)
                legs = legs0 + [nxt]
                odds = math.prod(base._odds(x) for x in legs)
                if odds > PROFILE_BANDS["LONGSHOT"][1]:
                    continue
                profile = _profile_for_odds(odds)
                if profile is not None and size <= PROFILE_MAX_LEGS[profile]:
                    built = _make_profile_builder(legs, profile, PickCls, pairs)
                    if built is not None:
                        sig = _signature(legs)
                        if sig not in seen_signatures:
                            seen_signatures.add(sig)
                            out.append(built)
                quick_prob = math.prod(base._prob(x) for x in legs)
                quick_ev = quick_prob * odds - 1.0
                score = quick_ev + 0.03 * min(size, 6) + 0.02 * min(base._prob(x) for x in legs)
                expanded.append((score, new_idxs))
        if not expanded:
            break
        expanded.sort(key=lambda item: item[0], reverse=True)
        beams = [idxs for _, idxs in expanded[:80]]
    return out


def expanded_builders(picks: Sequence[Any], props: Iterable[Any], PickCls: Any, base_extras: Sequence[Any] = ()) -> List[Any]:
    """Return up to one best builder per risk profile across all same-game pools."""
    pool = _candidate_pool(picks, props, PickCls)
    if not pool:
        return []
    groups: Dict[Tuple[str, str], List[Any]] = defaultdict(list)
    for c in pool:
        book, game = base._book(c), base._game(c)
        if book and game:
            groups[(book, game)].append(c)

    corr = base.safe_json_load(base.CORR_FILE, {}) or {}
    pairs = corr.get("pairs", {}) if isinstance(corr, dict) else {}
    candidates: List[Any] = []
    for group in groups.values():
        if len(group) < 2:
            continue
        candidates.extend(_beam_build(group, PickCls, pairs, max_legs=10))

    existing = {
        tuple(sorted(getattr(x, "legs", None) or []))
        for x in (base_extras or [])
        if getattr(x, "legs", None)
    }
    best: Dict[str, Any] = {}
    best_same_player: Optional[Any] = None
    for item in candidates:
        sig = tuple(sorted(getattr(item, "legs", None) or []))
        if sig in existing:
            continue
        profile = str((getattr(item, "features", {}) or {}).get("builder_profile") or "")
        old = best.get(profile)
        score = ((getattr(item, "ev", 0) or 0), (getattr(item, "probability", 0) or 0), len(getattr(item, "legs", []) or []))
        if old is None or score > ((getattr(old, "ev", 0) or 0), (getattr(old, "probability", 0) or 0), len(getattr(old, "legs", []) or [])):
            best[profile] = item
        if (getattr(item, "features", {}) or {}).get("same_player_multistat"):
            if best_same_player is None or score > ((getattr(best_same_player, "ev", 0) or 0), (getattr(best_same_player, "probability", 0) or 0), len(getattr(best_same_player, "legs", []) or [])):
                best_same_player = item

    result = [best[p] for p in ("safe", "value", "aggressive", "longshot") if p in best]
    if best_same_player is not None:
        sig = tuple(sorted(getattr(best_same_player, "legs", None) or []))
        if not any(tuple(sorted(getattr(x, "legs", None) or [])) == sig for x in result):
            result.append(best_same_player)
    return result[:5]


def install(base_builder_func):
    """Return a drop-in wrapper around the existing autonomous extras builder."""
    def wrapped(picks, props, PickCls, LadderLegCls):
        existing = list(base_builder_func(picks, props, PickCls, LadderLegCls) or [])
        extra = expanded_builders(picks, props, PickCls, existing)
        return existing + extra
    return wrapped
