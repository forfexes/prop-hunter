#!/usr/bin/env python3
"""Regression: US night-game kickoff (UTC next day) must not orphan ticket settlements."""
from prophunter_results import _result_context, _index_results, _match_result

source = {
    "player": "Jrue Holiday",
    "market": "Rebounds Over 3.5",
    "point": 3.5,
    "direction": "over",
    "date": "2020-11-16",
    "commence_time": "2020-11-17T01:10:00+00:00",
    "game": "POR Trail Blazers @ MIN Timberwolves",
}
assert _result_context(source)[0] == "2020-11-16", "UTC kickoff must not replace ticket date"
row = {
    "result_id": "night-fixture-regression",
    "result": "win", "actual_value": 4,
    "game_id": "official-nba-event",
    "pick_raw": source,
}
by_dedup, by_signature = _index_results([row])
leg = {
    "player": "Jrue Holiday", "market": "Rebounds Over 3.5",
    "point": 3.5, "direction": "over",
    "date": "2020-11-16",
    "game": "POR Trail Blazers @ MIN Timberwolves",
}
assert _match_result(leg, by_dedup, by_signature) is row, "Cross-game combo leg orphaned at midnight UTC"
assert _match_result(dict(leg, date="2020-11-14"), by_dedup, by_signature) is None, "Wrong previous fixture matched"
print("US NIGHT-GAME TICKET-DATE SETTLEMENT REGRESSION PASSED")
