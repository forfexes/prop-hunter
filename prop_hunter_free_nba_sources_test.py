from prop_hunter_free_nba_sources import SOURCES, collect_boxscorelab_seasons
import prop_hunter_free_nba_sources as m
assert SOURCES["boxscorelab"]["automated"] is True
assert all(not x["automated"] for k,x in SOURCES.items() if k != "boxscorelab")
old = m.download_season_csv
try:
    m.download_season_csv = lambda season: "player_name,season,games_played,usage_rate\nTest," + season + ",12,0.25\n"
    result = collect_boxscorelab_seasons(("2026-27", "2025-26"))
    assert len(result) == 2
    assert all(v["players"] == 1 and v["model_ready"] is False for v in result.values())
finally:
    m.download_season_csv = old
print("Free NBA source registry and season import tests passed")
