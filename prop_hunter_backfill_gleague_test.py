#!/usr/bin/env python3
from pathlib import Path
from prop_hunter_backfill_gleague import _row, KEEP

sample = {
    "SEASON_YEAR": "2025-26",
    "PLAYER_ID": 123,
    "PLAYER_NAME": "Test Guard",
    "TEAM_ID": 20,
    "TEAM_ABBREVIATION": "TST",
    "GAME_ID": "GLEAGUE-1",
    "GAME_DATE": "2026-01-15",
    "MATCHUP": "TST vs. OPP",
    "MIN": 31,
    "PTS": 24,
    "REB": 7,
    "AST": 9,
    "FG3M": 4,
    "STL": 2,
    "BLK": 1,
    "TOV": 3,
    "DD2": 1,
    "TD3": 0,
}
row = _row(sample, "2025-26")
assert row is not None
assert row["league"] == "NBA_G_LEAGUE"
assert row["sport"] == "BASKETBALL"
assert row["points"] == 24
assert row["rebounds"] == 7
assert row["assists"] == 9
assert row["pra"] == 40
assert row["ra"] == 16
assert row["pa"] == 33
assert row["pr"] == 31
assert row["opponent"] == "OPP"
assert row["double_double"] is True
assert row["triple_double"] is False
assert 30 <= KEEP <= 40

src = Path("prop_hunter_backfill_gleague.py").read_text(encoding="utf-8")
assert 'league_id_nullable="20"' in src
assert "last_n_games_nullable=KEEP" in src
assert "basketball/nba-g-league" in src
assert "PH_GLEAGUE_ESPN_DATES" in src
assert 'PH_GLEAGUE_NBA_API_FALLBACK", "0"' in src
assert '"sport,league,season,game_id,normalized_name"' in src

print("G LEAGUE BACKFILL TEST PASSED")
