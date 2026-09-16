#!/usr/bin/env python3
"""Curated source catalogue for PROP HUNTER.

The catalogue is deliberately broader than the active scraper set. Every source is
registered, health checked and placed into one of these modes:
ACTIVE, FALLBACK, RESEARCH, KEY_REQUIRED, BLOCKED or QUARANTINED.

Only public/free sources are active by default. Protected pages are never bypassed;
Playwright is used only as a normal browser fallback for publicly accessible pages.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List


@dataclass(frozen=True)
class SourceSpec:
    key: str
    name: str
    category: str
    access: str
    priority: int
    active_by_default: bool
    sports: tuple[str, ...]
    methods: tuple[str, ...]
    homepage: str
    notes: str = ""


SOURCES: tuple[SourceSpec, ...] = (
    # Live projection / pick'em sources
    SourceSpec("underdog", "Underdog", "live_props", "free_public", 100, True,
               ("MLB", "NBA", "WNBA", "NFL", "NHL"), ("json", "cache"),
               "https://underdogfantasy.com/", "Current strongest no-key source."),
    SourceSpec("prizepicks", "PrizePicks", "live_props", "free_public", 96, True,
               ("MLB", "NBA", "WNBA", "NFL", "NHL"), ("json", "cloudscraper", "playwright", "cache"),
               "https://www.prizepicks.com/"),
    SourceSpec("sleeper", "Sleeper Picks", "live_props", "free_public", 90, True,
               ("MLB", "NBA", "WNBA", "NFL", "NHL"), ("json", "cache"),
               "https://sleeper.com/"),
    SourceSpec("betr", "Betr Picks", "live_props", "free_public_web", 65, False,
               ("MLB", "NBA", "WNBA", "NFL", "NHL"), ("playwright", "cache"),
               "https://www.betr.app/"),
    SourceSpec("dabble", "Dabble", "live_props", "free_public_web", 62, False,
               ("MLB", "NBA", "WNBA", "NFL", "NHL"), ("playwright", "cache"),
               "https://dabble.com/"),
    SourceSpec("chalkboard", "Chalkboard", "live_props", "free_public_web", 58, False,
               ("MLB", "NBA", "WNBA", "NFL", "NHL"), ("playwright", "cache"),
               "https://chalkboard.io/"),
    SourceSpec("parlayplay", "ParlayPlay", "live_props", "free_public_web", 56, False,
               ("MLB", "NBA", "WNBA", "NFL", "NHL"), ("playwright", "cache"),
               "https://parlayplay.io/"),

    # Aggregated sportsbook odds / player props
    SourceSpec("oddspapi", "OddsPapi", "sportsbook_aggregator", "free_key_required", 99, True,
               ("MLB", "NBA", "WNBA", "NFL", "NHL"), ("official_json", "market_discovery", "cache"),
               "https://oddspapi.io/",
               "Dynamic sports/market discovery; real bookmaker lines and prices."),
    SourceSpec("sportsgameodds", "SportsGameOdds", "sportsbook_aggregator", "free_key_required", 98, True,
               ("MLB", "NBA", "WNBA", "NFL", "NHL", "NCAAB", "NCAAF"), ("official_json", "single_request_props", "cache"),
               "https://sportsgameodds.com/",
               "Optional key-gated source. One /v2/events league request can return bookmaker-level player props."),
    SourceSpec("propline", "PropLine", "sportsbook_aggregator", "free_key_required", 97, False,
               ("MLB", "NBA", "WNBA", "NFL", "NHL"), ("official_sdk", "alt_lines", "cache"),
               "https://prop-line.com/",
               "Watcher-qualified candidate: strong player-prop/alt-line coverage; keep disabled until an API key is configured and adapter is explicitly enabled."),

    # Sportsbooks / bookmakers
    SourceSpec("draftkings", "DraftKings", "sportsbook", "free_public_web", 92, True,
               ("MLB", "NBA", "WNBA", "NFL", "NHL"), ("json", "playwright", "cache"),
               "https://sportsbook.draftkings.com/"),
    SourceSpec("fanduel", "FanDuel", "sportsbook", "free_public_web", 91, True,
               ("MLB", "NBA", "WNBA", "NFL", "NHL"), ("json", "playwright", "cache"),
               "https://sportsbook.fanduel.com/"),
    SourceSpec("bovada", "Bovada", "sportsbook", "free_public_web", 89, True,
               ("MLB", "NBA", "WNBA", "NFL", "NHL"), ("json", "playwright", "cache"),
               "https://www.bovada.lv/sports"),
    SourceSpec("betmgm", "BetMGM", "sportsbook", "free_public_web", 82, False,
               ("MLB", "NBA", "WNBA", "NFL", "NHL"), ("playwright", "cache"),
               "https://sports.betmgm.com/"),
    SourceSpec("caesars", "Caesars Sportsbook", "sportsbook", "free_public_web", 81, False,
               ("MLB", "NBA", "WNBA", "NFL", "NHL"), ("playwright", "cache"),
               "https://sportsbook.caesars.com/"),
    SourceSpec("betrivers", "BetRivers", "sportsbook", "free_public_web", 79, False,
               ("MLB", "NBA", "WNBA", "NFL", "NHL"), ("playwright", "cache"),
               "https://www.betrivers.com/"),
    SourceSpec("superbook", "SuperBook", "sportsbook", "free_public_web", 68, False,
               ("MLB", "NBA", "WNBA", "NFL", "NHL"), ("playwright", "cache"),
               "https://www.superbook.com/"),
    SourceSpec("espn_bet", "ESPN BET", "sportsbook", "free_public_web", 67, True,
               ("MLB", "NBA", "WNBA", "NFL", "NHL"), ("json", "playwright", "cache"),
               "https://espnbet.com/"),
    SourceSpec("fanatics", "Fanatics Sportsbook", "sportsbook", "free_public_web", 64, False,
               ("MLB", "NBA", "WNBA", "NFL", "NHL"), ("playwright", "cache"),
               "https://sportsbook.fanatics.com/"),
    SourceSpec("hardrock", "Hard Rock Bet", "sportsbook", "free_public_web", 63, False,
               ("MLB", "NBA", "WNBA", "NFL", "NHL"), ("playwright", "cache"),
               "https://www.hardrock.bet/"),
    SourceSpec("thescore", "theScore Bet", "sportsbook", "free_public_web", 60, False,
               ("MLB", "NBA", "WNBA", "NFL", "NHL"), ("playwright", "cache"),
               "https://www.thescore.bet/"),
    SourceSpec("bet365", "bet365", "sportsbook", "protected_public_web", 88, True,
               ("MLB", "NBA", "WNBA", "NFL"),
               ("playwright_network", "websocket_json", "dom", "cache"),
               "https://www.bet365.com/",
               "Active browser fallback when normally accessible; no login/CAPTCHA/geo bypass."),
    SourceSpec("betfair", "Betfair Exchange", "exchange", "account_key_required", 40, False,
               ("MLB", "NBA", "WNBA", "NFL", "NHL"), ("official_api",),
               "https://developer.betfair.com/"),
    SourceSpec("pinnacle", "Pinnacle", "sportsbook", "restricted_access", 39, False,
               ("MLB", "NBA", "WNBA", "NFL", "NHL"), ("official_or_partner_api",),
               "https://www.pinnacle.com/"),

    # Consensus / historical
    SourceSpec("action_network", "Action Network", "consensus", "free_public_web", 45, False,
               ("MLB", "NBA", "WNBA", "NFL", "NHL"), ("json", "playwright", "cache"),
               "https://www.actionnetwork.com/"),
    SourceSpec("oddsportal", "OddsPortal", "historical_odds", "free_public_web", 44, False,
               ("MLB", "NBA", "WNBA", "NFL", "NHL"), ("playwright", "cache"),
               "https://www.oddsportal.com/", "Maintenance/backfill only."),

    # Official/free statistics and context
    SourceSpec("mlb_statsapi", "MLB StatsAPI", "official_stats", "free_public", 100, True,
               ("MLB",), ("json", "cache"), "https://statsapi.mlb.com/"),
    SourceSpec("statcast", "Baseball Savant / Statcast", "advanced_stats", "free_public", 98, True,
               ("MLB",), ("csv", "pybaseball", "cache"), "https://baseballsavant.mlb.com/"),
    SourceSpec("nba_api", "NBA.com / nba_api", "official_stats", "free_public", 98, True,
               ("NBA", "WNBA"), ("json", "python_library", "cache"), "https://www.nba.com/stats/"),
    SourceSpec("nba_live", "NBA Live CDN", "live_results", "free_public", 97, True,
               ("NBA", "WNBA"), ("json", "cache"), "https://cdn.nba.com/"),
    SourceSpec("nflverse", "nflverse / nflreadpy", "official_like_open_data", "free_public", 98, True,
               ("NFL",), ("parquet", "python_library", "cache"), "https://github.com/nflverse"),
    SourceSpec("espn", "ESPN public feeds", "schedule_results_context", "free_public_web", 86, True,
               ("MLB", "NBA", "WNBA", "NFL", "NHL"), ("json", "cache"), "https://www.espn.com/"),
    SourceSpec("nws", "US National Weather Service", "weather", "free_public", 80, True,
               ("MLB", "NFL"), ("official_api", "cache"), "https://www.weather.gov/documentation/services-web-api"),
    SourceSpec("thesportsdb", "TheSportsDB", "schedule_roster_fallback", "free_public", 55, True,
               ("MLB", "NBA", "WNBA", "NFL", "NHL"), ("json", "cache"), "https://www.thesportsdb.com/api.php"),
)


def as_rows() -> List[Dict[str, object]]:
    return [asdict(x) for x in SOURCES]


def by_key() -> Dict[str, SourceSpec]:
    return {x.key: x for x in SOURCES}


def active_keys() -> List[str]:
    return [x.key for x in SOURCES if x.active_by_default]
