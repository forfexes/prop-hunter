#!/usr/bin/env python3
"""
PROP HUNTER V10 — INTERNATIONAL LEAGUE CONFIG
"""

LEAGUES = {
    "BASEBALL": [
        {"league": "MLB", "country": "USA", "priority": 1, "history": "mlb_statsapi", "props_key": "baseball_mlb"},
        {"league": "KBO", "country": "Korea", "priority": 2, "history": "future_kbo", "props_key": "baseball_kbo"},
        {"league": "NPB", "country": "Japan", "priority": 3, "history": "future_npb", "props_key": "baseball_npb"},
        {"league": "CPBL", "country": "Taiwan", "priority": 4, "history": "future_cpbl", "props_key": "baseball_cpbl"},
        {"league": "WBC", "country": "International", "priority": 5, "history": "future_wbc", "props_key": "baseball_wbc"},
    ],
    "BASKETBALL": [
        {"league": "NBA", "country": "USA", "priority": 1, "history": "nba_api", "props_key": "basketball_nba"},
        {"league": "WNBA", "country": "USA", "priority": 2, "history": "espn_wnba", "props_key": "basketball_wnba"},
        {"league": "EUROLEAGUE", "country": "Europe", "priority": 3, "history": "future_euroleague", "props_key": "basketball_euroleague"},
        {"league": "ACB", "country": "Spain", "priority": 4, "history": "future_acb", "props_key": "basketball_spain_acb"},
        {"league": "EUROCUP", "country": "Europe", "priority": 5, "history": "future_eurocup", "props_key": "basketball_eurocup"},
        {"league": "NBL", "country": "Australia", "priority": 6, "history": "future_nbl", "props_key": "basketball_nbl"},
        {"league": "FIBA", "country": "International", "priority": 7, "history": "future_fiba", "props_key": "basketball_fiba"},
    ],
    "AMERICAN_FOOTBALL": [
        {"league": "NFL", "country": "USA", "priority": 1, "history": "nflverse", "props_key": "americanfootball_nfl"},
        {"league": "NCAAF", "country": "USA", "priority": 2, "history": "future_ncaaf", "props_key": "americanfootball_ncaaf"},
        {"league": "CFL", "country": "Canada", "priority": 3, "history": "future_cfl", "props_key": "americanfootball_cfl"},
        {"league": "UFL", "country": "USA", "priority": 4, "history": "future_ufl", "props_key": "americanfootball_ufl"},
        {"league": "ELF", "country": "Europe", "priority": 5, "history": "future_elf", "props_key": "americanfootball_elf"},
    ],
}

def all_leagues():
    out = []
    for sport, leagues in LEAGUES.items():
        for item in leagues:
            x = dict(item)
            x["sport"] = sport
            out.append(x)
    return out
