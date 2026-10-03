#!/usr/bin/env python3
from prop_hunter_backfill_shl import KEEP, parse_tables

assert 30 <= KEEP <= 40
tables=[
  [
    ["Player","SOG","Goals","Assists","Points","+/-","PIM","Hits","Blocks","FO","FO%","Shifts","TOI"],
    ["15 Jack Berglund","1","1","","1","+1","","1","1","0 - 5","00.00%","14","10:10"],
    ["18 Did Not Play","","","","","0","","","","","","",""],
  ],
  [
    ["Goalkeeper","Saves","GA","SWA","Saves%","PP SVS%","EQ SVS%","Shutout","PIM","TOI"],
    ["33 Emil Larmi","20","1","5","95.24%","80.00%","100.00%","","","40:00"],
  ],
  [
    ["Player","SOG","Goals","Assists","Points","+/-","PIM","Hits","Blocks","FO","FO%","Shifts","TOI"],
    ["81 Jan Mysak","1","1","","1","-1","","","1","8 - 4","66.67%","15","11:12"],
  ],
]
rows=parse_tables(tables,"20261003","FBK-HV71")
assert len(rows)==3, rows
jack=rows[0]
assert jack["team"]=="FBK" and jack["opponent"]=="HV71"
assert jack["goals"]==1 and jack["assists_hockey"]==0 and jack["shots_on_goal"]==1
assert jack["blocked_shots"]==1 and jack["raw"]["hits"]==1
goalie=rows[1]
assert goalie["goalie_saves"]==20 and goalie["minutes"]==40
mysak=rows[2]
assert mysak["team"]=="HV71" and mysak["goals"]==1
print("SHL BACKFILL TEST PASSED")
