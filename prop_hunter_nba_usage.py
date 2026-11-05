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

def safe_fetch_season_usage(season, timeout=12, logger=None):
    """Fail open for bot execution, fail closed for data quality.

    A blocked stats.nba.com endpoint must not create fake USG% or stop
    normal player-feature/settlement jobs.
    """
    try:
        return fetch_season_usage(season, timeout=timeout)
    except Exception as exc:
        if logger is not None:
            logger.warning("NBA official usage unavailable (%s): %s", type(exc).__name__, exc)
        return {}

def normalize_game_usage_rows(game_id, game_date, records):
    """Normalize official BoxScoreUsageV3 player rows; never infer missing usage."""
    if not isinstance(game_id, str) or not game_id.strip():
        raise ValueError("game_id required")
    if not isinstance(game_date, str) or len(game_date) != 10:
        raise ValueError("ISO game_date required")
    result = []
    for row in records:
        if not isinstance(row, dict):
            continue
        try:
            player_id = int(row.get("personId", row.get("PLAYER_ID")))
            raw = float(row.get("usagePercentage", row.get("USG_PCT")))
        except (ValueError, TypeError):
            continue
        if player_id <= 0 or not math.isfinite(raw) or not 0 <= raw <= 1:
            continue
        result.append({"player_id": player_id, "game_id": game_id,
                       "game_date": game_date, "usage_pct": round(raw * 100, 4),
                       "source": "nba_official_boxscore_usage_v3", "scope": "game"})
    return result


def player_usage_windows(game_rows, player_id):
    """True player-specific L5/L10/L15 from unique observed games only."""
    rows = [r for r in game_rows if r.get("player_id") == player_id
            and r.get("scope") == "game" and r.get("game_date") and r.get("game_id")
            and isinstance(r.get("usage_pct"), (float, int))
            and math.isfinite(r["usage_pct"]) and 0 <= r["usage_pct"] <= 100]
    rows.sort(key=lambda r: (r["game_date"], r["game_id"]), reverse=True)
    unique = []
    seen = set()
    for row in rows:
        if row["game_id"] not in seen:
            unique.append(row)
            seen.add(row["game_id"])
    result = {}
    for n in (5, 10, 15):
        sample = unique[:n]
        result[f"usage_l{n}"] = round(sum(r["usage_pct"] for r in sample) / len(sample), 4) if len(sample) == n else None
        result[f"usage_l{n}_observed"] = len(sample)
    return result
