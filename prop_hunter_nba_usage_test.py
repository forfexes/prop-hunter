from prop_hunter_nba_usage import normalize_usage_rows, fetch_season_usage
from unittest.mock import patch
rows=[{"PLAYER_ID":123,"PLAYER_NAME":"Fixture","USG_PCT":0.275},{"PLAYER_ID":124,"USG_PCT":float("nan")},{"PLAYER_ID":125,"USG_PCT":1.4},{"PLAYER_ID":0,"USG_PCT":0.2},{"PLAYER_ID":126,"USG_PCT":None}]
result=normalize_usage_rows(rows)
assert result=={123:{"player_id":123,"player_name":"Fixture","usage_pct":27.5,"source":"nba_official_advanced","scope":"season"}}
for bad in ("2026","bad","2026/27"):
    try:fetch_season_usage(bad)
    except ValueError:pass
    else:raise AssertionError(bad)
print("OFFICIAL NBA USAGE SOURCE NORMALIZATION / MISSING VALUE GUARDS PASSED")

from prop_hunter_nba_usage import safe_fetch_season_usage
with patch("prop_hunter_nba_usage.fetch_season_usage",side_effect=TimeoutError("NBA timeout")):
    assert safe_fetch_season_usage("2026-27")=={}
with patch("prop_hunter_nba_usage.fetch_season_usage",return_value={123:{"usage_pct":27.5}}):
    assert safe_fetch_season_usage("2026-27")[123]["usage_pct"]==27.5
print("NBA USAGE NETWORK FAILURE FALLBACK PASSED")

from prop_hunter_nba_usage import normalize_game_usage_rows, player_usage_windows
games=[]
for i in range(15):
    rows=normalize_game_usage_rows(f"00226{i:05d}", f"2026-10-{i+1:02d}",
        [{"personId":123,"usagePercentage":0.20+i/100},
         {"personId":456,"usagePercentage":float("nan")},
         {"personId":789,"usagePercentage":1.4}])
    assert len(rows)==1
    games+=rows
assert player_usage_windows(games,123)["usage_l5"]==32.0
assert player_usage_windows(games,123)["usage_l10"]==29.5
assert player_usage_windows(games,123)["usage_l15"]==27.0
assert player_usage_windows(games[:4],123)["usage_l5"] is None
assert player_usage_windows(games[:4],123)["usage_l5_observed"]==4
assert player_usage_windows(games+games,123)["usage_l15_observed"]==15
print("NBA OFFICIAL GAME USAGE WINDOWS PASSED")

from prop_hunter_nba_usage import fetch_game_usage, safe_fetch_game_usage
from types import ModuleType, SimpleNamespace
import sys
fake=ModuleType("nba_api")
stats=ModuleType("nba_api.stats")
endpoints=ModuleType("nba_api.stats.endpoints")
endpoints.boxscoreusagev3=SimpleNamespace(BoxScoreUsageV3=lambda **kw: SimpleNamespace(get_dict=lambda:{"boxScoreUsage":{"homeTeam":{"players":[{"personId":123,"usagePercentage":0.31}]},"awayTeam":{"players":[{"personId":456,"usagePercentage":0.19}]}}}))
with patch.dict(sys.modules,{"nba_api":fake,"nba_api.stats":stats,"nba_api.stats.endpoints":endpoints}):
    got=fetch_game_usage("0022600001","2026-10-28")
    assert {r["player_id"]:r["usage_pct"] for r in got}=={123:31.0,456:19.0},got
with patch("prop_hunter_nba_usage.fetch_game_usage",side_effect=TimeoutError):
    assert safe_fetch_game_usage("0022600001","2026-10-28")==[]
print("NBA OFFICIAL BOXSCORE USAGE FETCH CONTRACT PASSED")
