#!/usr/bin/env python3
"""Bounded, read-only 22bet LineFeed coverage probe; never publishes picks."""
import json
from prop_hunter_1xbet import _list_events, _league_ok, _game, parse_game, SPORT_IDS

HOST="https://22bet.com/service-api/LineFeed"
def probe(sports=("NBA","NHL","NFL")):
    out={}
    for sport in sports:
        sid=SPORT_IDS.get(sport)
        if not sid:
            out[sport]={"events":0,"matching":0,"observed_player_quotes":0}
            continue
        events=_list_events(HOST,sid)
        matching=[e for e in events if isinstance(e,dict) and _league_ok(sport,e)]
        quotes=[]
        detail_shapes=[]
        for ev in matching[:2]:
            eid=ev.get("I") or ev.get("CI") or ev.get("id")
            if eid:
                payload=_game(HOST,eid)
                value=(payload or {}).get("Value") if isinstance(payload,dict) else None
                if isinstance(value,dict):
                    subgame_titles=[str(x.get("TG") or x.get("PN") or x.get("N") or "")[:70] for x in (value.get("SG") or [])[:35] if isinstance(x,dict)]
                    detail_shapes.append({"subgame_titles":subgame_titles,"groups":len(value.get("GE") or []),"subgames":len(value.get("SG") or []),"event_outcomes":len(value.get("E") or []),"keys":sorted(value.keys())[:20]})
                quotes.extend(parse_game(payload,sport,ev,HOST))
        out[sport]={"events":len(events),"matching":len(matching),"observed_player_quotes":len(quotes),"detail_shapes":detail_shapes}
    return out
if __name__=="__main__":
    print(json.dumps(probe(),sort_keys=True))
