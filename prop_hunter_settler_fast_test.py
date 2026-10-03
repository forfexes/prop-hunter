#!/usr/bin/env python3
from prop_hunter_settler import build_log_index, find_gamelog

logs=[]
for i in range(2000):
    logs.append({
        "id": i+1,
        "player_name": f"Noise Player {i}",
        "normalized_name": f"noise player {i}",
        "game_id": f"noise-{i}",
        "game_date": "2026-10-01",
    })
logs.append({
    "id": 3001,
    "player_name": "Exact Player",
    "normalized_name": "exact player",
    "game_id": "game-123",
    "game_date": "2026-10-02",
    "points": 21,
})
idx=build_log_index(logs)
pick={"player":"Exact Player","game_id":"game-123","date":"2026-10-02"}
gl=find_gamelog(pick,logs,aliases={},log_index=idx)
assert gl and gl["game_id"]=="game-123", gl
assert len(idx["exact player"])==1
print("SETTLER FAST INDEX TEST PASSED")
