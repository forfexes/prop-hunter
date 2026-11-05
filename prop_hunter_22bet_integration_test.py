#!/usr/bin/env python3
"""22bet end-to-end normalization gate; never generates or publishes tips."""
from prop_hunter_22bet_points import parse_nba_points_subgame
from prop_hunter_source_orchestrator import _normalise
from prop_hunter_22bet_candidates import extract_candidates

EVENT={"I":123,"O1":"Phoenix Suns","O2":"Orlando Magic","S":"2026-11-07T02:00:00"}
PAYLOAD={"Value":{"GE":[{"E":[[
 {"PL":{"N":"Devin Booker","I":7230165},"P":25.5,"C":1.91,"T":1807},
 {"PL":{"N":"Devin Booker","I":7230165},"P":25.5,"C":1.83,"T":1806},
 {"PL":{"N":"Devin Booker"},"P":25.5,"C":1.5,"T":9999},
]]}]}}
def test_normalized_verified_points():
    raw=parse_nba_points_subgame(PAYLOAD,EVENT)
    assert len(raw)==2
    rows=[_normalise(x,"22bet_nba") for x in raw]
    assert all(rows),rows
    assert {r["direction"] for r in rows}=={"over","under"}
    assert all(r["market_key"]=="points" and r["bookmaker"]=="22bet" and r["odds_observed"] is True and r.get("observed_at") for r in rows)
    assert all(r["line"]==25.5 and r["player_name"]=="Devin Booker" for r in rows)

def test_unknown_nfl_not_published():
    raw={"Value":{"GE":[{"G":2627,"E":[[{"T":8397,"PL":{"N":"Trevor Lawrence"},"P":149.5,"C":1.87}]]}]}}
    candidates=extract_candidates(raw,league="NFL",event_id=123,subgame_title="Players' stats")
    assert len(candidates)==1 and candidates[0]["market_verified"] is False
    assert _normalise(candidates[0],"22bet_nfl") is None

if __name__=="__main__":
    test_normalized_verified_points();test_unknown_nfl_not_published()
    print("22bet end-to-end normalization and fail-closed tests passed")
