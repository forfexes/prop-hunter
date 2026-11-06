"""Offline fail-closed regression tests for BoxScore Lab seasonal fallback."""
from prop_hunter_boxscorelab import parse_season_csv

rows = parse_season_csv("player,season,games,usage_rate\nA,2026-27,10,0.265\nB,2026-27,1,0.17\n", "2026-27")
assert len(rows) == 2
assert rows[0]["usage_pct"] == 26.5
assert rows[0]["scope"] == "season"
assert "nba_player_id" not in rows[0] and "usage_l10" not in rows[0]
for bad in ("player,season,games,usage_rate\nA,2026-27,10,NaN\n",
            "player,season,games,usage_rate\nA,2026-27,10,-0.5\n",
            "player,season,games,usage_rate\nA,2026-27,10,999\n"):
    assert parse_season_csv(bad, "2026-27") == []
try:
    parse_season_csv("player,other\nA,3\n", "2026-27")
    raise AssertionError("missing column accepted")
except ValueError:
    pass
print("BoxScore Lab season source tests passed")
