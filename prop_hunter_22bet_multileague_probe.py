#!/usr/bin/env python3
"""Read-only 22bet multi-league discovery. No inferred markets or published odds."""
import json
from prop_hunter_1xbet import _list_events, _game, SPORT_IDS
from prop_hunter_22bet_points import parse_nba_points_subgame
HOST="https://22bet.com/service-api/LineFeed"
LEAGUES={
 "NBA":(SPORT_IDS["NBA"],("nba","national basketball association")),
 "NCAAB":(SPORT_IDS["NBA"],("ncaa","college basketball","ncaab")),
 "NCAAF":(SPORT_IDS["NFL"],("ncaa","college football","ncaaf")),
 "MLB":(SPORT_IDS["MLB"],("mlb","major league baseball")),
 "NFL":(SPORT_IDS["NFL"],("nfl","national football league")),
 "NHL":(SPORT_IDS["NHL"],("nhl","national hockey league")),
 "WNBA":(SPORT_IDS["WNBA"],("wnba",)),
 "EUROBASKET":(SPORT_IDS["NBA"],("eurobasket","euro basket","european basketball championship")),
 "EUROLEAGUE":(SPORT_IDS["NBA"],("euroleague","euro league")),
 "AHL":(SPORT_IDS["NHL"],("ahl","american hockey league")),
 "SHL":(SPORT_IDS["NHL"],("shl","swedish hockey league")),
 "SWISS_NL":(SPORT_IDS["NHL"],("national league","swiss national league")),
}
def discover():
    result={}
    event_cache={}
    for league,(sport_id,keywords) in LEAGUES.items():
        if sport_id not in event_cache: event_cache[sport_id]=_list_events(HOST,sport_id)
        events=event_cache[sport_id]
        matches=[e for e in events if isinstance(e,dict) and any(k in " ".join(str(e.get(f) or "") for f in ("LE","L","League","O1","O2")).lower() for k in keywords)]
        details=[]
        for ev in matches[:1]:
            eid=ev.get("I") or ev.get("CI")
            if not eid: continue
            game=_game(HOST,eid)
            if not game: game=_game(HOST,eid)
            val=(game or {}).get("Value") if isinstance(game,dict) else None
            if not isinstance(val,dict):continue
            subs=[x for x in val.get("SG") or [] if isinstance(x,dict)]
            selected=[x for x in subs if any(t in str(x.get("TG") or x.get("PN") or "").lower() for t in ("player","stat","shot","strikeout","rebound","assist","point","yard","touchdown","hit","base"))][:3]
            subdata=[]
            for sub in selected:
                subid=sub.get("CI") or sub.get("I")
                if not subid:continue
                data=_game(HOST,subid)
                if not data: data=_game(HOST,subid)
                v=(data or {}).get("Value") if isinstance(data,dict) else None
                groups=(v or {}).get("GE") or [] if isinstance(v,dict) else []
                types={}
                player_fields=0
                samples={}
                for g in groups:
                    if not isinstance(g,dict):continue
                    for bucket in g.get("E") or []:
                        for o in (bucket if isinstance(bucket,list) else [bucket]):
                            if not isinstance(o,dict):continue
                            typ=str(o.get("T"))
                            types[typ]=types.get(typ,0)+1
                            if typ not in samples and len(samples)<25:
                                pl=o.get("PL")
                                samples[typ]={"player":str(pl.get("N") or "")[:50] if isinstance(pl,dict) else "","line":o.get("P"),"price":o.get("C"),"group":o.get("G"),"player_team":pl.get("T") if isinstance(pl,dict) else None}
                            if isinstance(o.get("PL"),dict) and o["PL"].get("N"):player_fields+=1
                subdata.append({"title":str(sub.get("TG") or sub.get("PN") or "")[:55],"groups":len(groups),"player_named_outcomes":player_fields,"outcome_types":dict(sorted(types.items(),key=lambda p:-p[1])[:12]),"type_samples":samples})
            details.append({"subgames":len(subs),"candidate_subgames":subdata,"event_league":str(ev.get("LE") or ev.get("L") or "")[:90],"event_teams":[str(ev.get("O1") or "")[:65],str(ev.get("O2") or "")[:65]]})
        result[league]={"catalog_events":len(events),"matching_events":len(matches),"details":details,"status":"no_matching_events" if not matches else ("inspected_with_market_data" if any(any(s.get("player_named_outcomes",0)>0 for s in d.get("candidate_subgames",[])) for d in details) else "market_data_unavailable")}
    return result
if __name__=="__main__":print(json.dumps(discover(),sort_keys=True))
