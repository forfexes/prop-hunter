"""Verified-source intake policy for NBA contextual player-prop evidence.

Research catalogue, not an automated scraper. Only explicitly observed, dated
and identified numeric records may enter features. No external HTTP in this file,
no Supabase writes, and no change to pick selection or Telegram.
"""
from datetime import date
from math import isfinite

SOURCES = {
    "nba_stats": ("https://www.nba.com/stats", "official", "requires_live_probe"),
    "nba_usage": ("https://www.nba.com/stats/players/usage", "official_usage", "blocked_on_actions"),
    "nbastuffer_formula": ("https://www.nbastuffer.com/analytics101/usage-rate/", "definition", "reference_only"),
    "simulnba_formula": ("https://www.simulnba.com/definitions/usage-rate", "definition", "unverified"),
    "nuvela_formula": ("https://nuvela.ai/nba/glossary/usage-rate", "definition", "reference_only"),
    "fantasypros_dvp": ("https://www.fantasypros.com/daily-fantasy/nba/fanduel-defense-vs-position.php", "dvp_boxscore", "manual_review"),
    "rotowire_dvp": ("https://www.rotowire.com/daily/nba/defense-vspos.php", "dvp", "manual_review"),
    "fantasyteamadvice_dvp": ("https://fantasyteamadvice.com/nba/dvp", "dvp_fantasy_points", "manual_review"),
    "fantasyteamadvisors_dvp": ("https://fantasyteamadvisors.com/nba/nba-pts-allowed-by-position/", "dvp_points", "manual_review"),
    "nba_events": ("https://www.nba.com/stats/events", "shot_events", "requires_live_probe"),
    "nbashotcharts": ("https://www.nbashotcharts.net/", "shot_chart", "unverified"),
    "hashtag_shots": ("https://hashtagbasketball.com/nba-shot-profile", "shot_profile", "unverified"),
    "hoopology_shots": ("https://hoopologyviz.com/shooting-profile", "shot_profile", "manual_review"),
    "nba_offensive_rebounds": ("https://www.nba.com/stats/players/offensive-rebounding", "tracking", "requires_live_probe"),
    "opta_orb": ("https://theanalyst.com/articles/offensive-rebounding-increase-nba-2025-2026", "research", "reference_only"),
    "nbaanalytic_orb": ("https://nbaanalytic.com/articles/offensive-rebounding-and-second-chance-points.html", "research", "reference_only"),
    "orb_github": ("https://github.com/jakekosowsky/offensive-rebounding-analysis", "research_code", "unverified"),
    "basketball_reference": ("https://www.basketball-reference.com", "historical", "manual_review"),
    "cleaning_the_glass": ("https://cleaningtheglass.com", "advanced", "subscription_review"),
    "dunks_and_threes": ("https://dunksandthrees.com", "advanced", "subscription_review"),
    "pbpstats": ("https://www.pbpstats.com", "play_by_play", "manual_review"),
    "statmuse": ("https://www.statmuse.com", "research", "manual_review"),
    "swishanalytics": ("https://swishanalytics.com", "props", "subscription_review"),
    "props_cash": ("https://props.cash", "props", "subscription_review"),
    "rotogrinders": ("https://rotogrinders.com", "dfs", "subscription_review"),
}
POSITIONS = frozenset(("PG", "SG", "SF", "PF", "C"))
DVP_STATS = frozenset(("points", "rebounds", "assists", "threes"))
SHOT_STATS = frozenset(("attempts", "makes", "zone"))


def observed_dvp(row, *, as_of, max_age_days=8):
    """Validate imported raw PTS/REB/AST/3PM allowed, never fantasy points.

    Explicit season and game sample are mandatory. Returns None on ambiguity.
    Source terms and permissions must be checked separately before collection.
    """
    if not isinstance(row, dict) or row.get("source") not in {"fantasypros_dvp", "verified_official_dvp"}:
        return None
    team = str(row.get("opponent_team") or "").upper()
    pos = str(row.get("position") or "").upper()
    stat = str(row.get("stat") or "").lower()
    if len(team) != 3 or not team.isalpha() or pos not in POSITIONS or stat not in DVP_STATS:
        return None
    try:
        sample = int(row["games"])
        val = float(row["allowed_per_game"])
        season = str(row["season"])
        published = date.fromisoformat(str(row["observed_on"]))
        today = date.fromisoformat(str(as_of))
        if not (sample >= 5 and 0 <= val <= 150 and isfinite(val)
                and 0 <= (today - published).days <= max_age_days and len(season) == 7
                and season[4] == "-" and season[:4].isdigit() and season[5:].isdigit()):
            return None
    except (ValueError, TypeError, KeyError, OverflowError):
        return None
    return {"opponent_team": team, "position": pos, "stat": stat,
            "allowed_per_game": val, "games": sample,
            "season": season, "observed_on": published.isoformat(),
            "source": row["source"], "model_ready": False}
