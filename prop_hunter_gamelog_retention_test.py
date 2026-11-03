#!/usr/bin/env python3
import prop_hunter_gamelog_retention as _ret
# Test ist deterministisch für KEEP=15, unabhängig von der Job-Umgebung
# (Daily-Control setzt z.B. PH_GAMELOG_KEEP_PER_PLAYER=40 global).
_ret.KEEP = 15
from prop_hunter_gamelog_retention import rank_delete_ids

rows=[]
rid=1
for player,count in (("alpha",45),("beta",12)):
    for day in range(count):
        rows.append({
            "id": rid,
            "sport": "BASKETBALL",
            "league": "NBA",
            "normalized_name": player,
            "game_date": f"2026-01-{(day%28)+1:02d}",
            "created_at": f"2026-01-{(day%28)+1:02d}T00:00:00+00:00",
        })
        rid += 1

ids=rank_delete_ids(rows)
assert len(ids)==30, ids
assert all(i <= 45 for i in ids)
assert not any(i > 45 for i in ids)
print("RETENTION TEST PASSED")
