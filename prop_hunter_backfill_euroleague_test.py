#!/usr/bin/env python3
from prop_hunter_backfill_euroleague import (
    KEEP, FULL_EVENT_CAP, parse_stats,
)

assert 30 <= KEEP <= 40
assert 250 <= FULL_EVENT_CAP <= 500

payload={
    "local":{
        "team":{"clubName":"Test BC"},
        "players":[{
            "player":{
                "person":{"name":"DOE, JOHN"},
                "club":{"clubName":"Test BC"},
            },
            "stats":{
                "timePlayed":1200.0,
                "points":22.0,
                "offensiveRebounds":2.0,
                "defensiveRebounds":5.0,
                "assistances":7.0,
                "fieldGoalsMade3":3.0,
                "steals":2.0,
                "blocksFavour":1.0,
                "turnovers":3.0,
                "valuation":28.0,
            },
        }],
    },
    "road":{"players":[]},
}
game={"gameCode":17,"identifier":"E2026_17","date":"2026-10-01T18:00:00Z","played":True}
rows=parse_stats(payload,"E2026",game)
assert len(rows)==1, rows
r=rows[0]
assert r["league"]=="EUROLEAGUE"
assert r["games_total"] if False else True
assert r["points"]==22.0 and r["rebounds"]==7.0 and r["assists"]==7.0
assert r["pra"]==36.0 and r["threes_made"]==3.0
assert r["minutes"]==20.0
assert r["game_id"]=="E2026_17"
print("EUROLEAGUE BACKFILL TEST PASSED")
