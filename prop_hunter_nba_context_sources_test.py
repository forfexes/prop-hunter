"""No inferred defense values, stale stats, or fantasy totals in NBA context."""
from prop_hunter_nba_context_sources import SOURCES, observed_dvp
assert len(SOURCES) == 25
row = dict(source="fantasypros_dvp",opponent_team="BOS",position="PG",
           stat="assists",allowed_per_game=7.2,games=15,season="2026-27",
           observed_on="2026-11-17")
good=observed_dvp(row,as_of="2026-11-17")
assert good and good["model_ready"] is False and good["allowed_per_game"] == 7.2
for change in ({"stat":"fantasy_points"},{"position":"ALL"},{"games":2},
               {"allowed_per_game":float("nan")},{"allowed_per_game":-3},
               {"source":"fantasyteamadvice_dvp"},{"observed_on":"2026-10-01"}):
    assert observed_dvp(dict(row,**change),as_of="2026-11-17") is None, change
assert observed_dvp(row,as_of="2026-11-10") is None
print("NBA CONTEXT OBSERVATION GUARD PASSED")
