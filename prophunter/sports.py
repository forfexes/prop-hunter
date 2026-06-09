"""Sport / market definitions."""
from __future__ import annotations

from typing import Dict, List, NamedTuple, Optional


class Market(NamedTuple):
    key: str
    label: str
    min_point: Optional[float]
    min_odds: float


class SportCfg(NamedTuple):
    emoji: str
    name: str
    markets: List[Market]


SPORTS: Dict[str, SportCfg] = {
    "baseball_mlb": SportCfg(emoji="⚾", name="MLB", markets=[
        Market("batter_home_runs",      "Home Run",        None, 3.5),
        Market("batter_hits",           "Hits Over 1.5",   None, 1.7),
        Market("batter_total_bases",    "Total Bases",     None, 1.8),
        Market("pitcher_strikeouts",    "Pitcher K",       None, 1.8),
        Market("batter_stolen_bases",   "Stolen Base",     None, 4.0),
        Market("batter_rbis",           "RBI",             None, 2.5),
        Market("pitcher_outs",          "Outs Recorded",   None, 1.8),
        Market("pitcher_earned_runs",   "Earned Runs U",   None, 1.8),
        Market("pitcher_hits_allowed",  "Hits Allowed U",  None, 1.8),
    ]),
    "basketball_nba": SportCfg(emoji="🏀", name="NBA", markets=[
        Market("player_rebounds_assists",        "Rebounds+Assists", 10,   1.8),
        Market("player_points_rebounds_assists", "PRA",              35,   1.8),
        Market("player_points_rebounds",         "PR",               30,   1.8),
        Market("player_points_assists",          "PA",               30,   1.8),
        Market("player_rebounds_alternate",      "Rebounds",          8,   1.9),
        Market("player_assists_alternate",       "Assists",           6,   1.9),
        Market("player_threes_alternate",        "3PM",               2,   1.9),
        Market("player_double_double",           "Double Double",  None,   2.5),
        Market("player_points_alternate",        "Points",           25,   3.5),
        Market("player_blocks_alternate",        "Blocks",            2,   3.5),
        Market("player_steals_alternate",        "Steals",            2,   3.5),
        Market("player_triple_double",           "Triple Double",  None,   6.0),
    ]),
    "basketball_wnba": SportCfg(emoji="🏀", name="WNBA", markets=[
        Market("player_rebounds_assists",        "Rebounds+Assists",  8,  1.8),
        Market("player_points_rebounds_assists", "PRA",              20,  1.8),
        Market("player_points_rebounds",         "PR",               18,  1.8),
        Market("player_points_assists",          "PA",               18,  1.8),
        Market("player_points_alternate",        "Points",           15,  3.5),
        Market("player_rebounds_alternate",      "Rebounds",          6,  1.9),
        Market("player_assists_alternate",       "Assists",           5,  1.9),
        Market("player_threes_alternate",        "3PM",               2,  2.0),
        Market("player_double_double",           "Double Double",  None,  2.5),
    ]),
    "basketball_euroleague": SportCfg(emoji="🏀", name="Euroleague", markets=[
        Market("player_points_alternate",   "Points",   12, 3.0),
        Market("player_rebounds_alternate", "Rebounds",  5, 2.8),
        Market("player_assists_alternate",  "Assists",   4, 2.8),
        Market("player_threes_alternate",   "3PM",       2, 2.5),
    ]),
    "americanfootball_nfl": SportCfg(emoji="🏈", name="NFL", markets=[
        Market("player_anytime_td",              "Anytime TD",  None, 2.5),
        Market("player_pass_tds_alternate",      "Pass TDs",    None, 3.0),
        Market("player_pass_yds_alternate",      "Pass Yds",    None, 1.8),
        Market("player_rush_yds_alternate",      "Rush Yds",    None, 3.0),
        Market("player_reception_yds_alternate", "Rec Yds",     None, 3.0),
        Market("player_receptions_alternate",    "Receptions",  None, 1.8),
    ]),
}


def sport_by_emoji(emoji: str) -> str:
    for cfg in SPORTS.values():
        if cfg.emoji == emoji:
            return cfg.name
    return "UNKNOWN"
