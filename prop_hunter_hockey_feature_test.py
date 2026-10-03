#!/usr/bin/env python3
import prop_hunter_feature_builder as fb

rows = [
    {"goals": 1, "assists_hockey": 1, "hockey_points": 2, "shots_on_goal": 4, "goalie_saves": None, "blocked_shots": 2},
    {"goals": 0, "assists_hockey": 1, "hockey_points": 1, "shots_on_goal": 2, "goalie_saves": None, "blocked_shots": 1},
]
assert fb.avg(rows, "goals") == 0.5
assert fb.avg(rows, "assists_hockey") == 1
assert fb.avg(rows, "hockey_points") == 1.5
assert fb.avg(rows, "shots_on_goal") == 3
assert fb.hit(rows, "goals", 0.5) == 0.5
assert fb.hit(rows, "shots_on_goal", 2.5) == 0.5
for stat in ("goals","assists_hockey","hockey_points","shots_on_goal","goalie_saves","blocked_shots","power_play_points"):
    assert stat in fb.STATS, stat
print("HOCKEY FEATURE TEST PASSED")
