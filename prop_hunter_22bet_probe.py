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
        subgame_details=[]
        for ev in matching[:2]:
            eid=ev.get("I") or ev.get("CI") or ev.get("id")
            if eid:
                payload=_game(HOST,eid)
                value=(payload or {}).get("Value") if isinstance(payload,dict) else None
                if isinstance(value,dict):
                    subgame_titles=[str(x.get("TG") or x.get("PN") or x.get("N") or "")[:70] for x in (value.get("SG") or [])[:35] if isinstance(x,dict)]
                    detail_shapes.append({"subgame_titles":subgame_titles,"groups":len(value.get("GE") or []),"subgames":len(value.get("SG") or []),"event_outcomes":len(value.get("E") or []),"keys":sorted(value.keys())[:20]})
                quotes.extend(parse_game(payload,sport,ev,HOST))
                if isinstance(value,dict):
                    for sub in (value.get("SG") or []):
                        if not isinstance(sub,dict): continue
                        title=str(sub.get("TG") or sub.get("PN") or sub.get("N") or "")
                        if not any(x in title.lower() for x in ("players\u0027 stats","rebounds","assists","shots on goal")): continue
                        sub_id=sub.get("CI") or sub.get("I")
                        if not sub_id: continue
                        sub_payload=_game(HOST,sub_id)
                        sub_value=(sub_payload or {}).get("Value") if isinstance(sub_payload,dict) else None
                        sub_rows=parse_game(sub_payload,sport,ev,HOST)
                        quotes.extend(sub_rows)
                        subgame_details.append({"title":title[:50],"groups":len((sub_value or {}).get("GE") or []) if isinstance(sub_value,dict) else 0,"quotes":len(sub_rows),"sample_groups":[{"keys":sorted(g.keys())[:15],"name":str(g.get("GS") or g.get("Name") or g.get("GN") or "")[:70],"outcome_count":len(g.get("E") or [])} for g in ((sub_value or {}).get("GE") or [])[:3] if isinstance(g,dict)]})
                        if len(subgame_details)>=8: break
        out[sport]={"events":len(events),"matching":len(matching),"observed_player_quotes":len(quotes),"detail_shapes":detail_shapes,"subgame_details":subgame_details}
    return out
if __name__=="__main__":
    print(json.dumps(probe(),sort_keys=True))
