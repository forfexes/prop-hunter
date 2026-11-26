import datetime as dt
from prop_hunter_nba_usage_mirror_probe import validate
today=dt.date(2026,11,24)
row={"game_id":"0022600001","game_date":"2026-11-23","player_id":"123","team_id":"1","min":32,"usg_pct":.27,"win":True}
other={**row,"player_id":"456","team_id":"2","win":False}
assert validate([row,other],today)["observations"]==2
assert validate([row],today)["observations"]==0
assert validate([row,{**other,"usg_pct":27}],today)["observations"]==0
assert validate([row,{**other,"min":0}],today)["observations"]==0
try:
    validate([row,other,row],today)
except ValueError:
    pass
else:
    raise AssertionError("duplicate player/game accepted")
print("Mirror usage provenance and fixture validation passed")
