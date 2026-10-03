#!/usr/bin/env python3
from prop_hunter_backfill_swiss_nl import _display_name,_minutes,_skater_rows,_goalie_rows,KEEP

assert 30<=KEEP<=40
assert _display_name("Geering Patrick")=="Patrick Geering"
assert _display_name("von Rohr Manuel")=="Manuel von Rohr"
assert _minutes("13:50")>13.8

sk=[{"No":"4","Spieler":"Geering Patrick","Pos":"Verteidiger","G":"1","A":"2","PTS":"3","PIM Total":"0","+/-":"2","SOG":"4","SHM Total":"1","SHP Total":"0","BkS":"2","FOW Total":"0","FOL Total":"0","FO%":"0.00","TOI Total":"13:50","TOI PP":"00:10","TOI PK":"01:18"}]
r=_skater_rows(sk,"20271105000049","2026-09-29","gamePlayerStatsHome")[0]
assert r["player_name"]=="Patrick Geering" and r["goals"]==1 and r["assists_hockey"]==2
assert r["shots_on_goal"]==4 and r["blocked_shots"]==2

g=[{"No":"30","Spieler":"Hrubec Simon","GA":"3","SVS":"25","SA":"28","SVS%":"89.29","MIP":"60:00","GAA":"3","PIM":"0"}]
gr=_goalie_rows(g,"20271105000049","2026-09-29","gameGoalieStatsHome")[0]
assert gr["player_name"]=="Simon Hrubec" and gr["goalie_saves"]==25 and gr["minutes"]==60
print("SWISS NL BACKFILL TEST PASSED")
