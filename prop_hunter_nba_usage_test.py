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
