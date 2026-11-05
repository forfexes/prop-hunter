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
        for ev in matching[:2]:
            eid=ev.get("I") or ev.get("CI") or ev.get("id")
            if eid:
                quotes.extend(parse_game(_game(HOST,eid),sport,ev,HOST))
        out[sport]={"events":len(events),"matching":len(matching),"observed_player_quotes":len(quotes)}
    return out
if __name__=="__main__":
    print(json.dumps(probe(),sort_keys=True))
