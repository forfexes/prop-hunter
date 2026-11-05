from prop_hunter_22bet_candidates import extract_candidates

def test_nhl():
    data={"Value":{"GE":[{"G":1679,"E":[[{"T":5551,"PL":{"N":"Zach Werenski","I":1},"P":0.5,"C":1.54}]]}]}}
    rows=extract_candidates(data,league="NHL",event_id=12,subgame_title="Shots On Goal")
    assert len(rows)==1
    assert rows[0]["player"]=="Zach Werenski"
    assert rows[0]["type_id"]==5551 and rows[0]["group_id"]==1679
    assert rows[0]["market_verified"] is False

def test_nfl():
    data={"Value":{"GE":[{"G":2627,"E":[[{"T":8397,"PL":{"N":"Trevor Lawrence"},"P":149.5,"C":1.05}]]}]}}
    rows=extract_candidates(data,league="NFL",event_id=1,subgame_title="Players' stats")
    assert len(rows)==1 and rows[0]["line"]==149.5
    assert rows[0]["market_verified"] is False

def test_reject():
    data={"Value":{"GE":[{"E":[[{"T":8397,"P":149.5,"C":1.05},{"T":8397,"PL":{"N":"X"},"C":0.9}]]}]}}
    assert extract_candidates(data,league="NFL",event_id=1,subgame_title="Players' stats")==[]

if __name__=="__main__":
    test_nhl();test_nfl();test_reject();print("22bet NFL NHL candidate tests passed")
