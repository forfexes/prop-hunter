"""Optional official NBA USG% season snapshot. No fabricated per-game usage."""
import math

def normalize_usage_rows(records):
    result = {}
    for row in records:
        try:
            player_id = int(row["PLAYER_ID"])
            fraction = float(row["USG_PCT"])
        except (KeyError, ValueError, TypeError):
            continue
        if player_id <= 0 or not math.isfinite(fraction) or not 0 <= fraction <= 1:
            continue
        result[player_id] = {
            "player_id": player_id,
            "player_name": row.get("PLAYER_NAME"),
            "usage_pct": round(fraction * 100, 4),
            "source": "nba_official_advanced",
            "scope": "season",
        }
    return result

def fetch_season_usage(season, timeout=20):
    """Official NBA advanced dashboard, keyed by NBA player ID.

    Season-level aggregate, NOT per-player L5/L10/L15 game usage.
    Fail closed if nba.com blocks or times out; caller can retry later.
    """
    if not isinstance(season, str) or len(season) != 7 or season[4] != "-" or not (season[:4] + season[5:]).isdigit():
        raise ValueError("season must be YYYY-YY")
    from nba_api.stats.endpoints import leaguedashplayerstats
    response = leaguedashplayerstats.LeagueDashPlayerStats(
        season=season,
        season_type_all_star="Regular Season",
        measure_type_detailed_defense="Advanced",
        per_mode_detailed="PerGame",
        timeout=timeout,
    )
    return normalize_usage_rows(response.get_normalized_dict().get("LeagueDashPlayerStats", []))
