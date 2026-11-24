"""League-verified PROP HUNTER picture lookup identities.

A generic sport such as ICE_HOCKEY is not an NHL identity. Honor the league
stored alongside every roster entry. Where the configured ESPN provider does
not cover that league, return a precise, truthful provider gap, not a guessed
NHL player/team picture. These helpers perform no HTTP requests or publishing.
"""
from __future__ import annotations

from typing import Iterable

ESPN_LEAGUES = {
    "NBA": ("basketball", "nba"),
    "WNBA": ("basketball", "wnba"),
    "NCAAB": ("basketball", "mens-college-basketball"),
    "EUROLEAGUE": ("basketball", "euroleague"),
    "NFL": ("football", "nfl"),
    "NCAAF": ("football", "college-football"),
    "MLB": ("baseball", "mlb"),
    "NHL": ("hockey", "nhl"),
}
EXTERNAL_LEAGUES = {
    "SWISS_NL", "SWISS_SL", "SHL", "AHL", "DEL", "LIIGA",
    "KHL", "ALLSVENSKAN", "CZECH_EXTRALIGA",
}
GENERIC_SPORTS = {"ICE_HOCKEY", "HOCKEY", "BASKETBALL", "BASEBALL",
                  "FOOTBALL", "AMERICAN_FOOTBALL", "SOCCER", "UNKNOWN"}

# These are exact and independently known team/abbreviation equivalents.
# Never infer from a city name or similarity across competitions.
_TEAM_ALIASES = {
    "NBA": {"UTA": "Utah Jazz", "PHO SUNS": "Phoenix Suns",
            "LA LAKERS": "Los Angeles Lakers", "LA CLIPPERS": "Los Angeles Clippers"},
    "NHL": {"LAK": "Los Angeles Kings", "SJS": "San Jose Sharks",
            "TBL": "Tampa Bay Lightning",
            "VGS GOLDEN KNIGHTS": "Vegas Golden Knights",
            "VGK": "Vegas Golden Knights"},
    "NFL": {"NY JETS": "New York Jets", "NYJ": "New York Jets"},
    "MLB": {"CWS": "Chicago White Sox", "CHW": "Chicago White Sox"},
}
_KNOWN_NBA_TEAMS = {
    "UTAH JAZZ", "BOSTON CELTICS", "SACRAMENTO KINGS", "PHOENIX SUNS",
    "NEW ORLEANS PELICANS", "LOS ANGELES LAKERS", "LOS ANGELES CLIPPERS",
}
_KNOWN_NBL_TEAMS = {"ADELAIDE 36ERS", "ILLAWARRA HAWKS"}


def _key(value):
    return " ".join(str(value or "").replace("_", " ").upper().split())


def resolve_provider(sport, competitions: Iterable[str] = ()):
    """Return (ESPN league or None, reason, declared league).

    Multi-competition entries are not silently collapsed. An explicit league
    wins over the generic sport; incompatible explicit specific codes fail.
    """
    declared = {_key(c).replace(" ", "_") for c in competitions if _key(c)}
    if len(declared) > 1:
        return None, "league_multiple:" + ",".join(sorted(declared)), None
    explicit = next(iter(declared), "")
    sport_key = _key(sport).replace(" ", "_")
    if explicit and sport_key in ESPN_LEAGUES and explicit != sport_key:
        return None, "league_sport_conflict:" + sport_key + "/" + explicit, explicit
    effective = explicit or (sport_key if sport_key in ESPN_LEAGUES else "")
    if effective in ESPN_LEAGUES:
        return ESPN_LEAGUES[effective], "provider_supported", effective
    if effective in EXTERNAL_LEAGUES:
        return None, "league_provider_not_configured:" + effective, effective
    if effective:
        return None, "league_provider_unknown:" + effective, effective
    return None, "league_missing", None


def normalized_team(team, league_code):
    """Return (safe query name or None, reason) in its declared league."""
    league_code = _key(league_code).replace(" ", "_")
    name = str(team or "").strip()
    if not name:
        return None, "team_missing"
    norm = _key(name)
    if norm in _KNOWN_NBA_TEAMS and league_code != "NBA":
        return None, "team_league_conflict:NBA/" + str(league_code)
    if norm in _KNOWN_NBL_TEAMS and league_code == "EUROLEAGUE":
        return None, "team_league_conflict:NBL/EUROLEAGUE"
    canonical = _TEAM_ALIASES.get(league_code, {}).get(norm)
    if canonical:
        return canonical, "verified_alias"
    return name, "exact_source_name"
