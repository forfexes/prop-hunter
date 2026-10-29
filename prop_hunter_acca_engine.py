#!/usr/bin/env python3
"""Cross-game ACCA engine for PROP HUNTER.

Builds multi-game accumulators only from independently observed bookmaker rows
that already pass the normal positive-EV candidate guard. It never invents a
single-leg line or price. The displayed accumulator price is the product of
observed single-leg prices and is explicitly marked as derived so users can
confirm the final bookmaker quote before placement.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Sequence, Tuple

import prop_hunter_builder_engine as base

PROFILE_BANDS = {
    "safe": (2.0, 5.0),
    "value": (5.0, 15.0),
    "aggressive": (15.0, 50.0),
    "lottery": (50.0, 300.0),
}
PROFILE_MAX_LEGS = {"safe": 3, "value": 5, "aggressive": 7, "lottery": 10}
PROFILE_MIN_LEG_PROB = {"safe": 0.50, "value": 0.36, "aggressive": 0.22, "lottery": 0.10}
PROFILE_MIN_EV = {"safe": 0.02, "value": 0.035, "aggressive": 0.055, "lottery": 0.08}
PROFILE_FRACTION = {"safe": 0.15, "value": 0.10, "aggressive": 0.05, "lottery": 0.02}
PROFILE_CAP = {"safe": 0.45, "value": 0.25, "aggressive": 0.12, "lottery": 0.05}
PROFILE_FLOOR = {"safe": 0.20, "value": 0.12, "aggressive": 0.07, "lottery": 0.03}


def _profile_for_odds(odds: float) -> str:
    for name, (lo, hi) in PROFILE_BANDS.items():
        if lo <= odds < hi or (name == "lottery" and math.isclose(odds, hi)):
            return name
    return ""


def _family(obj: Any) -> str:
    m = base._base_market(getattr(obj, "market", ""))
    aliases = {
        "anytime td": "touchdowns",
        "anytime touchdown scorer": "touchdowns",
        "td": "touchdowns",
        "tds": "touchdowns",
        "home run": "home_runs",
        "home runs": "home_runs",
        "hr": "home_runs",
        "runs batted in": "rbi",
        "3pm": "threes",
        "three pointers": "threes",
    }
    return aliases.get(m, m.replace(" ", "_"))


def _eligible(obj: Any) -> bool:
    # Temporary product rule: no UNDER legs in cross-game builders/ACCAs.
    if base._direction(obj) != "over":
        return False
    if not base._real_price(obj) or base._odds(obj) <= 1.01 or base._prob(obj) <= 0:
        return False
    sport = base._sport(obj)
    fam = _family(obj)
    allowed = {
        "NFL": {"touchdowns", "passing_touchdowns", "rushing_touchdowns", "receiving_touchdowns", "receptions", "receiving_yards", "rushing_yards", "passing_yards"},
        "MLB": {"home_runs", "rbi", "total_bases", "pitcher_strikeouts", "hits", "runs", "stolen_bases"},
        "NBA": {"points", "rebounds", "assists", "threes", "double_double", "triple_double", "pra", "ra", "pa", "pr"},
        "WNBA": {"points", "rebounds", "assists", "threes", "double_double", "triple_double", "pra", "ra", "pa", "pr"},
        "EUROLEAGUE": {"points", "rebounds", "assists", "threes", "double_double", "triple_double", "pra", "ra", "pa", "pr"},
        "NCAAB": {"points", "rebounds", "assists", "threes", "double_double"},
    }
    return fam in allowed.get(sport, set())


def _pool(picks: Sequence[Any], props: Iterable[Any], PickCls: Any) -> List[Any]:
    out: List[Any] = []
    seen = set()
    for p in picks or []:
        if getattr(p, "type", None) != "single" or not _eligible(p):
            continue
        key = base._candidate_key(p)
        if key not in seen:
            seen.add(key); out.append(p)
    for prop in props or []:
        c = base._candidate_from_prop(prop, PickCls)
        if c is None or not _eligible(c):
            continue
        key = base._candidate_key(c)
        if key not in seen:
            seen.add(key); out.append(c)
    return out


def _compatible(legs: Sequence[Any], nxt: Any) -> bool:
    if not legs:
        return True
    if base._book(nxt) != base._book(legs[0]) or base._sport(nxt) != base._sport(legs[0]):
        return False
    # This engine is intentionally cross-game. One leg per event keeps the
    # probability estimate conservative and avoids accidental SGP semantics.
    game = base._game(nxt)
    if not game or any(base._game(x) == game for x in legs):
        return False
    # Do not repeat the same player across an accumulator.
    if base._player(nxt).lower() in {base._player(x).lower() for x in legs}:
        return False
    return True


def _joint_probability(legs: Sequence[Any]) -> float:
    independent = math.prod(base._prob(x) for x in legs)
    # No positive cross-game correlation is assumed. Add a small uncertainty
    # haircut for every extra leg because markets and model errors are not fully independent.
    penalty = 0.97 ** max(0, len(legs) - 1)
    return max(0.0005, min(0.95, independent * penalty))


def _make(legs: Sequence[Any], profile: str, PickCls: Any) -> Any:
    odds = math.prod(base._odds(x) for x in legs)
    prob = _joint_probability(legs)
    edge = prob * odds - 1.0
    if edge < PROFILE_MIN_EV[profile]:
        return None
    if min(base._prob(x) for x in legs) < PROFILE_MIN_LEG_PROB[profile]:
        return None
    stake = base._kelly(prob, odds, PROFILE_FRACTION[profile], PROFILE_CAP[profile])
    stake = max(PROFILE_FLOOR[profile], min(PROFILE_CAP[profile], stake))
    sport = base._sport(legs[0]); book = base._book(legs[0])
    label = {"safe":"SAFE ACCA", "value":"VALUE ACCA", "aggressive":"AGGRESSIVE ACCA", "lottery":"LOTTERY ACCA"}[profile]
    built = PickCls(
        type="betbuilder",
        category=f"acca_{profile}",
        tier=1 if profile in {"safe", "value"} else 2,
        player=" + ".join(base._player(x) for x in legs),
        team="",
        emoji="🧩",
        market=f"{len(legs)}-Leg {label}",
        direction="over",
        odds=round(odds, 2),
        stake=round(stake, 2),
        probability=round(prob, 5),
        edge_pct=round(edge * 100.0, 1),
        ev=round(edge, 4),
        game="MULTI-GAME",
        analysis=(f"{label} · {len(legs)} echte +EV Legs · {sport} · {book} · "
                  "Cross-Game, konservative Unabhängigkeits-Haircut; finale ACCA-Quote beim Book prüfen"),
        legs=[base._leg_text(x) for x in legs],
    )
    built.sport = sport
    built.leg_details = [{
        "player": base._player(x), "sport": base._sport(x), "market": getattr(x, "market", ""),
        "market_family": _family(x), "direction": base._direction(x), "point": base._point(x),
        "odds": base._odds(x), "probability": base._prob(x), "bookmaker": base._book(x),
        "game": base._game(x),
    } for x in legs]
    built.features = {
        "odds_observed": False,
        "price_type": "derived_acca",
        "bookmaker": book,
        "builder_profile": profile,
        "combo_scope": "cross_game",
        "leg_count": len(legs),
        "acca_odds_estimated_from_legs": True,
        "builder_odds_estimated_from_legs": True,
    }
    return built


def cross_game_accas(picks: Sequence[Any], props: Iterable[Any], PickCls: Any) -> List[Any]:
    pool = _pool(picks, props, PickCls)
    groups: Dict[Tuple[str, str], List[Any]] = defaultdict(list)
    for c in pool:
        book, sport = base._book(c), base._sport(c)
        if book and sport:
            groups[(book, sport)].append(c)

    best: Dict[str, Any] = {}
    for group in groups.values():
        # Keep several strong alternatives per event in the search pool.
        # Final ACCAs still enforce one leg per event via _compatible().
        event_options: Dict[str, List[Any]] = defaultdict(list)
        for c in sorted(group, key=lambda x: (base._prob(x), base._prob(x) * base._odds(x) - 1.0), reverse=True):
            game = base._game(c)
            if game and len(event_options[game]) < 4:
                event_options[game].append(c)
        ranked = sorted(
            [c for rows in event_options.values() for c in rows],
            key=lambda x: (base._prob(x), base._prob(x) * base._odds(x) - 1.0),
            reverse=True,
        )[:28]
        beams = [(i,) for i in range(len(ranked))]
        for size in range(2, min(10, len(ranked)) + 1):
            expanded = []
            for idxs in beams:
                legs0 = [ranked[i] for i in idxs]
                for j in range(idxs[-1] + 1, len(ranked)):
                    nxt = ranked[j]
                    if not _compatible(legs0, nxt):
                        continue
                    legs = legs0 + [nxt]
                    odds = math.prod(base._odds(x) for x in legs)
                    if odds > PROFILE_BANDS["lottery"][1]:
                        continue
                    profile = _profile_for_odds(odds)
                    if profile and size <= PROFILE_MAX_LEGS[profile]:
                        built = _make(legs, profile, PickCls)
                        if built is not None:
                            score = (built.ev, built.probability, len(legs))
                            old = best.get(profile)
                            old_score = (getattr(old, "ev", -9), getattr(old, "probability", 0), len(getattr(old, "legs", []) or [])) if old else (-9,0,0)
                            if score > old_score:
                                best[profile] = built
                    quick = _joint_probability(legs) * odds - 1.0
                    expanded.append((quick, idxs + (j,)))
            if not expanded:
                break
            expanded.sort(key=lambda x: x[0], reverse=True)
            beams = [idxs for _, idxs in expanded[:60]]
    return [best[k] for k in ("safe", "value", "aggressive", "lottery") if k in best]


def install(base_builder_func):
    """Drop-in wrapper; preserves all existing SGP/ladder behavior."""
    def wrapped(picks, props, PickCls, LadderLegCls):
        existing = list(base_builder_func(picks, props, PickCls, LadderLegCls) or [])
        return existing + cross_game_accas(picks, props, PickCls)
    return wrapped
