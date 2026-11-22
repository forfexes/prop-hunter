"""Conservative NBA fixture/player-team integrity for original Telegram cards.

Only an independently named NBA club and a fully parsed two-team NBA fixture
are compared. Unknown aliases do not become guessed identities. A definite
Philadelphia 76ers player must not be shown on a Boston-Sacramento tip.
"""
from __future__ import annotations

import re
import unicodedata

_NBA = (
    ("ATL", "Atlanta Hawks", "Hawks"),
    ("BOS", "Boston Celtics", "Celtics"),
    ("BKN", "Brooklyn Nets", "Nets"),
    ("CHA", "Charlotte Hornets", "Hornets"),
    ("CHI", "Chicago Bulls", "Bulls"),
    ("CLE", "Cleveland Cavaliers", "Cavaliers"),
    ("DAL", "Dallas Mavericks", "Mavericks"),
    ("DEN", "Denver Nuggets", "Nuggets"),
    ("DET", "Detroit Pistons", "Pistons"),
    ("GSW", "Golden State Warriors", "Warriors"),
    ("HOU", "Houston Rockets", "Rockets"),
    ("IND", "Indiana Pacers", "Pacers"),
    ("LAC", "Los Angeles Clippers", "Clippers"),
    ("LAL", "Los Angeles Lakers", "Lakers"),
    ("MEM", "Memphis Grizzlies", "Grizzlies"),
    ("MIA", "Miami Heat", "Heat"),
    ("MIL", "Milwaukee Bucks", "Bucks"),
    ("MIN", "Minnesota Timberwolves", "Timberwolves"),
    ("NOP", "New Orleans Pelicans", "Pelicans"),
    ("NYK", "New York Knicks", "Knicks"),
    ("OKC", "Oklahoma City Thunder", "Thunder"),
    ("ORL", "Orlando Magic", "Magic"),
    ("PHI", "Philadelphia 76ers", "76ers"),
    ("PHX", "Phoenix Suns", "Suns"),
    ("POR", "Portland Trail Blazers", "Trail Blazers"),
    ("SAC", "Sacramento Kings", "Kings"),
    ("SAS", "San Antonio Spurs", "Spurs"),
    ("TOR", "Toronto Raptors", "Raptors"),
    ("UTA", "Utah Jazz", "Jazz"),
    ("WAS", "Washington Wizards", "Wizards"),
)


def _norm(value):
    plain = unicodedata.normalize("NFKD", str(value or "").lower())
    plain = "".join(ch for ch in plain if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "", plain)


_ALIASES = {}
for abbreviation, full, nickname in _NBA:
    for alias in (abbreviation, full, nickname, f"{abbreviation} {nickname}"):
        _ALIASES[_norm(alias)] = abbreviation
_ALIASES.update({
    "phosuns": "PHX", "phosuns": "PHX",
    "gswarriors": "GSW", "goldenstate": "GSW",
    "saspurs": "SAS", "sanantonio": "SAS",
    "nopelicans": "NOP", "neworleans": "NOP",
    "nyknicks": "NYK", "newyork": "NYK",
    "laslakers": "LAL", "laclippers": "LAC",
    "sixers": "PHI", "philadelphiasixers": "PHI",
    "trailblazers": "POR", "blazers": "POR",
})


def nba_code(team):
    return _ALIASES.get(_norm(team))


def definite_team_fixture_conflict(player_team, fixture):
    """True only when ALL 3 team names unambiguously map to NBA franchises."""
    if not player_team or not fixture:
        return False
    names = re.split(r"\s+(?:vs\.?|@|-)\s+", str(fixture), maxsplit=1, flags=re.I)
    if len(names) != 2:
        return False
    club, home, away = (nba_code(player_team), nba_code(names[0]), nba_code(names[1]))
    return bool(club and home and away and club not in (home, away))
