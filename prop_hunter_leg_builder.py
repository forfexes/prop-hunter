#!/usr/bin/env python3
"""
PROP HUNTER V10 — 1-5 LEG BUILDER

Baut:
- market-spezifische Builder: HR, TD, DD, RBA, PRA, Hits usw.
- Cross-Sport Builder: HR + TD + DD + RBA usw.
- keine künstlichen Limits für Kandidaten; Legs werden nur aus passed Picks gebaut.
"""

from itertools import combinations
from math import prod

try:
    from prop_hunter_rules import classify_pick, CROSS_SPORT_BUILDERS
except Exception:
    classify_pick = None
    CROSS_SPORT_BUILDERS = set()

def _f(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default

def _player_key(p):
    return str(getattr(p, "player", "") or getattr(p, "player_name", "") or "").lower().strip()

def _game_key(p):
    return str(getattr(p, "game", "") or "").lower().strip()

def _odds(p):
    return _f(getattr(p, "odds", 0), 0)

def _prob(p):
    return _f(getattr(p, "probability", 0), 0)

def _edge(p):
    return _f(getattr(p, "edge_pct", 0), 0)

def combo_score(legs):
    # Priorität: jedes Leg Value, dann Edge/Prob Balance
    return sum(_edge(x) for x in legs) + sum(_prob(x) * 10 for x in legs)

def combo_odds(legs):
    o = 1.0
    for p in legs:
        oo = _odds(p)
        if oo <= 1.01:
            return 0
        o *= oo
    return round(o, 2)

def combo_prob(legs):
    p = 1.0
    for x in legs:
        pp = _prob(x)
        if pp <= 0:
            return 0
        p *= pp
    return round(p, 4)

def valid_combo(legs):
    players = [_player_key(x) for x in legs]
    if len(players) != len(set(players)):
        return False

    # Verhindere offensichtliche Konflikte: Pitcher K gegen Batter Hit/HR im gleichen Game später erweiterbar.
    return True

def group_passed_picks(picks):
    grouped = {}
    for p in picks or []:
        info = classify_pick(p) if classify_pick else {"passed": True, "builder": "UNKNOWN", "allowed_legs": [1]}
        if not info.get("passed"):
            continue
        builder = info.get("builder", "UNKNOWN")
        grouped.setdefault(builder, []).append((p, info))
    return grouped

def build_market_specific_legs(picks):
    out = []
    grouped = group_passed_picks(picks)
    for builder, items in grouped.items():
        pure = [p for p, info in items]
        allowed = sorted(set(x for _, info in items for x in info.get("allowed_legs", [1])))
        for leg_count in allowed:
            if leg_count <= 1:
                continue
            if len(pure) < leg_count:
                continue
            for legs in combinations(pure, leg_count):
                if not valid_combo(legs):
                    continue
                out.append({
                    "type": "combo",
                    "builder_type": builder,
                    "leg_count": leg_count,
                    "legs": list(legs),
                    "odds": combo_odds(legs),
                    "probability": combo_prob(legs),
                    "score": combo_score(legs),
                })
    out.sort(key=lambda x: x["score"], reverse=True)
    return out

def build_cross_sport_legs(picks, max_leg_count=5):
    passed = []
    for p in picks or []:
        info = classify_pick(p) if classify_pick else {"passed": True, "builder": "UNKNOWN", "allowed_legs": [1]}
        if not info.get("passed"):
            continue
        if info.get("builder") not in CROSS_SPORT_BUILDERS:
            continue
        passed.append((p, info))

    out = []
    pure = [p for p, _ in passed]
    for leg_count in range(2, max_leg_count + 1):
        if len(pure) < leg_count:
            continue
        for legs in combinations(pure, leg_count):
            if not valid_combo(legs):
                continue
            builders = []
            for x in legs:
                info = classify_pick(x)
                builders.append(info.get("builder"))
            # Cross-Sport/Market nur wenn nicht alles derselbe Builder
            if len(set(builders)) < 2:
                continue
            out.append({
                "type": "combo",
                "builder_type": "CROSS_SPORT",
                "leg_count": leg_count,
                "legs": list(legs),
                "odds": combo_odds(legs),
                "probability": combo_prob(legs),
                "score": combo_score(legs),
            })
    out.sort(key=lambda x: x["score"], reverse=True)
    return out
