#!/usr/bin/env python3
"""Opt-in 22bet NBA points source. Bounded, direct observed prices only."""
import os
from prop_hunter_1xbet import _list_events, _game, _league_ok, SPORT_IDS
from prop_hunter_22bet_points import parse_nba_points_subgame

HOST="https://22bet.com/service-api/LineFeed"
def configured():
    return os.getenv("PH_22BET_ENABLED","0").strip().lower() in ("1","true","yes","on")
def fetch_22bet_nba_points(max_events=2):
    if not configured(): return []
    events=_list_events(HOST,SPORT_IDS["NBA"])
    candidates=[e for e in events if isinstance(e,dict) and _league_ok("NBA",e)]
    rows=[]
    for ev in candidates[:max(1,min(int(max_events),3))]:
        eid=ev.get("I") or ev.get("CI")
        if not eid: continue
        payload=_game(HOST,eid)
        val=(payload or {}).get("Value") if isinstance(payload,dict) else None
        if not isinstance(val,dict): continue
        for sub in val.get("SG") or []:
            if not isinstance(sub,dict): continue
            if str(sub.get("TG") or sub.get("PN") or sub.get("N") or "").strip().lower()!="players' stats": continue
            sid=sub.get("CI") or sub.get("I")
            if not sid: continue
            subval=_game(HOST,sid)
            # First 'Players stats' subgame is points in the verified NBA sample.
            # Restrict to one subgame per event until full market-id mapping verified.
            rows.extend(parse_nba_points_subgame(subval,ev,HOST))
            break
    return rows
