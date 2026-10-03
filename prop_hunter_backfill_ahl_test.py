#!/usr/bin/env python3
from prop_hunter_backfill_ahl import _clean_jsonp, profile_to_rows, KEEP

assert _clean_jsonp('cb({"SiteKit":{"current_season_id":92}});')["SiteKit"]["current_season_id"] == 92
assert _clean_jsonp('cb([{"x":1}]);')[0]["x"] == 1

player = {
    "_player_id": "1234",
    "_player_name": "Test Skater",
    "teamCode": "TST",
}
profile = {
    "SiteKit": {
        "gameByGame": [{
            "sections": [{
                "data": [{
                    "prop": {"game": {"gameLink": "1029999"}},
                    "row": {
                        "date_played": "2026-10-02",
                        "shots": "5",
                        "goals": "1",
                        "assists": "2",
                        "points": "3",
                        "pp": "1",
                        "sh": "0",
                        "gw": "0",
                        "game": "TST @ OPP",
                    },
                }]
            }]
        }]
    }
}
rows = profile_to_rows(profile, player, 92)
assert len(rows) == 1
r = rows[0]
assert r["league"] == "AHL"
assert r["sport"] == "ICE_HOCKEY"
assert r["game_id"] == "1029999"
assert r["game_date"] == "2026-10-02"
assert r["goals"] == 1
assert r["assists_hockey"] == 2
assert r["hockey_points"] == 3
assert r["shots_on_goal"] == 5
assert r["raw"]["player_id"] == "1234"
assert 30 <= KEEP <= 40
print("AHL BACKFILL TEST PASSED")
