#!/usr/bin/env python3
"""
PROP HUNTER V10 — MARKET RULE MATRIX

Vision:
- keine künstlichen Pick-Limits
- Condition erfüllt = rein
- market-spezifische 1–5 Leg Builder
- Cross-Sport Builder erlaubt, wenn jedes Leg einzeln Value hat
"""

import re

RULES = {
    # Baseball
    "MLB_HR": {"category":"HR_HUNTER", "builder":"HR", "legs":[1,2,3,4,5], "min_prob":0.10, "min_edge":8.0, "min_odds":4.00, "risk":"high"},
    "MLB_HITS": {"category":"HITS_VALUE", "builder":"HITS", "legs":[1,2,3,4], "min_prob":0.56, "min_edge":3.0, "min_odds":1.40, "risk":"medium"},
    "MLB_TOTAL_BASES": {"category":"BASES_VALUE", "builder":"BASES", "legs":[1,2,3], "min_prob":0.54, "min_edge":4.0, "min_odds":1.55, "risk":"medium"},
    "MLB_PITCHER_K": {"category":"K_VALUE", "builder":"PITCHER_K", "legs":[1,2,3], "min_prob":0.56, "min_edge":4.0, "min_odds":1.55, "risk":"medium"},

    # Basketball
    "BASKET_RA": {"category":"RBA_VALUE", "builder":"RBA", "legs":[1,2,3], "min_prob":0.56, "min_edge":4.0, "min_odds":1.55, "risk":"medium"},
    "BASKET_PRA": {"category":"PRA_VALUE", "builder":"PRA", "legs":[1,2,3], "min_prob":0.57, "min_edge":4.0, "min_odds":1.55, "risk":"medium"},
    "BASKET_ASSISTS": {"category":"AST_VALUE", "builder":"ASSISTS", "legs":[1,2,3], "min_prob":0.56, "min_edge":4.0, "min_odds":1.55, "risk":"medium"},
    "BASKET_REBOUNDS": {"category":"REB_VALUE", "builder":"REBOUNDS", "legs":[1,2,3], "min_prob":0.56, "min_edge":3.5, "min_odds":1.55, "risk":"medium"},
    "BASKET_POINTS": {"category":"PTS_VALUE", "builder":"POINTS", "legs":[1,2], "min_prob":0.58, "min_edge":5.0, "min_odds":1.60, "risk":"medium"},
    "NBA_DOUBLE_DOUBLE": {"category":"DD_SPECIAL", "builder":"DOUBLE_DOUBLE", "legs":[1,2,3], "min_prob":0.18, "min_edge":8.0, "min_odds":1.50, "risk":"high"},
    "NBA_TRIPLE_DOUBLE": {"category":"TD_SPECIAL", "builder":"TRIPLE_DOUBLE", "legs":[1,2,3], "min_prob":0.04, "min_edge":12.0, "min_odds":5.00, "risk":"very_high"},

    # American Football
    "NFL_TD": {"category":"TD_HUNTER", "builder":"TOUCHDOWN", "legs":[1,2,3,4,5], "min_prob":0.12, "min_edge":8.0, "min_odds":1.80, "risk":"high"},
    "NFL_FIRST_TD": {"category":"FIRST_TD_LOTTERY", "builder":"FIRST_TD", "legs":[1,2,3], "min_prob":0.03, "min_edge":15.0, "min_odds":7.00, "risk":"very_high"},
    "NFL_2PLUS_TD": {"category":"TWO_PLUS_TD", "builder":"TWO_PLUS_TD", "legs":[1,2], "min_prob":0.04, "min_edge":15.0, "min_odds":6.00, "risk":"very_high"},
    "NFL_RECEIVING": {"category":"REC_VALUE", "builder":"RECEIVING", "legs":[1,2,3], "min_prob":0.55, "min_edge":5.0, "min_odds":1.55, "risk":"medium"},
    "NFL_RUSHING": {"category":"RUSH_VALUE", "builder":"RUSHING", "legs":[1,2,3], "min_prob":0.55, "min_edge":5.0, "min_odds":1.55, "risk":"medium"},
    "NFL_PASSING": {"category":"PASS_VALUE", "builder":"PASSING", "legs":[1,2], "min_prob":0.56, "min_edge":5.0, "min_odds":1.55, "risk":"medium"},
}

CROSS_SPORT_BUILDERS = {
    "HR", "TOUCHDOWN", "DOUBLE_DOUBLE", "TRIPLE_DOUBLE", "RBA", "PRA",
    "HITS", "BASES", "PITCHER_K", "RECEIVING", "RUSHING"
}

def _n(x):
    return str(x or "").lower().strip()

def get_market_group(p):
    market = _n(getattr(p, "market", ""))
    sport = str(getattr(p, "source_sport", "") or getattr(p, "sport", "") or "").upper()

    if "home run" in market or re.search(r"\bhr\b", market):
        return "MLB_HR"
    if "strikeout" in market or "pitcher k" in market:
        return "MLB_PITCHER_K"
    if "total base" in market or "bases" in market:
        return "MLB_TOTAL_BASES"
    if "hit" in market:
        return "MLB_HITS"

    if "triple-double" in market or "triple double" in market:
        return "NBA_TRIPLE_DOUBLE"
    if "double-double" in market or "double double" in market:
        return "NBA_DOUBLE_DOUBLE"
    if "rebounds+assists" in market or "reb+ast" in market or "rba" in market:
        return "BASKET_RA"
    if "pra" in market or "points+rebounds+assists" in market:
        return "BASKET_PRA"
    if "assist" in market:
        return "BASKET_ASSISTS"
    if "rebound" in market:
        return "BASKET_REBOUNDS"
    if "point" in market:
        return "BASKET_POINTS"

    if "first touchdown" in market or "first td" in market:
        return "NFL_FIRST_TD"
    if "2+ td" in market or "2+ touchdown" in market:
        return "NFL_2PLUS_TD"
    if "touchdown" in market or "anytime td" in market or re.search(r"\btd\b", market):
        return "NFL_TD"
    if "receiving" in market or "reception" in market:
        return "NFL_RECEIVING"
    if "rushing" in market:
        return "NFL_RUSHING"
    if "passing" in market:
        return "NFL_PASSING"

    return f"{sport}_OTHER"

def rule_id_for_pick(p):
    sport = str(getattr(p, "source_sport", "") or getattr(p, "sport", "") or "").upper()
    league = str(getattr(p, "league", "") or "")
    group = get_market_group(p)
    direction = str(getattr(p, "direction", "over") or "over").upper()
    return f"{sport}:{league}:{group}:{direction}"

def classify_pick(p):
    group = get_market_group(p)
    rule = RULES.get(group)
    if not rule:
        return {"passed": False, "reject_reason": "no_rule", "market_group": group, "category": "UNKNOWN", "builder": "UNKNOWN", "allowed_legs": [1], "rule": None}

    prob = float(getattr(p, "probability", 0) or 0)
    edge = float(getattr(p, "edge_pct", 0) or 0)
    odds = float(getattr(p, "odds", 0) or 0)
    point = getattr(p, "point", None)

    if group.startswith("BASKET") and point is None:
        return {"passed": False, "reject_reason": "missing_line", "market_group": group, "category": rule["category"], "builder": rule["builder"], "allowed_legs": rule["legs"], "rule": rule}
    if prob < rule["min_prob"]:
        return {"passed": False, "reject_reason": "prob_low", "market_group": group, "category": rule["category"], "builder": rule["builder"], "allowed_legs": rule["legs"], "rule": rule}
    if edge < rule["min_edge"]:
        return {"passed": False, "reject_reason": "edge_low", "market_group": group, "category": rule["category"], "builder": rule["builder"], "allowed_legs": rule["legs"], "rule": rule}
    if odds < rule["min_odds"]:
        return {"passed": False, "reject_reason": "odds_low", "market_group": group, "category": rule["category"], "builder": rule["builder"], "allowed_legs": rule["legs"], "rule": rule}

    return {"passed": True, "reject_reason": None, "market_group": group, "category": rule["category"], "builder": rule["builder"], "allowed_legs": rule["legs"], "rule": rule}
