from prop_hunter_22bet_points import parse_nba_points_subgame
from datetime import datetime,timezone
event={"I":123,"O1":"Phoenix Suns","O2":"Orlando Magic","S":"2026-11-06T03:00:00"}
def test_booker():
    payload={"Value":{"GE":[{"E":[[{"PL":{"N":"Devin Booker","I":7230165},"P":25.5,"C":1.91,"T":1807},{"PL":{"N":"Devin Booker","I":7230165},"P":25.5,"C":1.83,"T":1806},{"P":25.5,"C":1.8,"T":1807}]]}]}}
    rows=parse_nba_points_subgame(payload,event)
    assert len(rows)==2,rows
    assert all(r["odds_observed"] is True for r in rows)
    assert all((datetime.now(timezone.utc)-datetime.fromisoformat(r["observed_at"])).total_seconds()<60 for r in rows)
    assert [(r["player_name"],r["direction"],r["line"],r["odds_decimal"]) for r in rows]==[("Devin Booker","over",25.5,1.91),("Devin Booker","under",25.5,1.83)]
def test_reject_unknown():
    payload={"Value":{"GE":[{"E":[[{"PL":{"N":"Player"},"P":15.5,"C":2,"T":9999},{"PL":{"N":"Player"},"P":15.5,"C":0,"T":1807}]]}]}}
    assert parse_nba_points_subgame(payload,event)==[]
if __name__=="__main__":
    test_booker();test_reject_unknown();print("22bet points regression passed")
