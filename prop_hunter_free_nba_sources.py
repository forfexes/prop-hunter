"""Free NBA source registry and safe multi-season collection.

Only BoxScore Lab has a verified, automated, license-compatible CSV endpoint.
Other providers remain explicit import-only adapters until access is validated.
Never interpret season usage as game-level L5/L10/L15.
"""
from prop_hunter_boxscorelab import download_season_csv, parse_season_csv

SOURCES = {
    "boxscorelab": {"mode": "live_csv", "cost": 0, "scope": "season", "automated": True},
    "basketball_reference": {"mode": "verified_csv_import", "cost": 0, "scope": "season", "automated": False},
    "nbastuffer": {"mode": "verified_csv_import", "cost": 0, "scope": "season", "automated": False},
    "databallr": {"mode": "verified_csv_import", "cost": 0, "scope": "season", "automated": False},
    "statyx": {"mode": "manual_free_csv", "cost": 0, "scope": "selected_window", "automated": False},
    "fantasydata": {"mode": "unverified_access", "cost": 0, "scope": "season", "automated": False},
    "nba_official": {"mode": "official_endpoint_timeout", "cost": 0, "scope": "game_or_season", "automated": False},
}


def collect_boxscorelab_seasons(seasons=("2026-27", "2025-26", "2024-25", "2023-24", "2022-23")):
    result = {}
    for season in seasons:
        rows = parse_season_csv(download_season_csv(season), season)
        if not rows:
            raise ValueError("empty verified season " + season)
        result[season] = {"players": len(rows), "source": "boxscorelab_csv_cc_by_4_0",
                          "scope": "season", "model_ready": False}
    return result


if __name__ == "__main__":
    import json
    print(json.dumps({"sources": SOURCES, "seasons": collect_boxscorelab_seasons()}, sort_keys=True))
