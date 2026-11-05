#!/usr/bin/env python3
"""Conservative 22bet NBA player points parser. No unverified market mappings."""
from __future__ import annotations
import math

def parse_nba_points_subgame(payload, event, host="https://22bet.com"):
    value=(payload or {}).get("Value") if isinstance(payload,dict) else None
    if not isinstance(value,dict): return []
    groups=value.get("GE") or []
    if not isinstance(groups,list) or not groups: return []
    # First Players' stats subgame is NBA points, established by comparing
    # observed Booker 25.5 1.91/1.83 against the operator's market screen.
    # Only the first group, with known paired over/under outcome types.
    group=groups[0]
    if not isinstance(group,dict): return []
    outcomes=group.get("E") or []
    result=[]
    for bucket in outcomes:
        for e in (bucket if isinstance(bucket,list) else [bucket]):
            if not isinstance(e,dict): continue
            pl=e.get("PL")
            if not isinstance(pl,dict): continue
            player=str(pl.get("N") or "").strip()
            typ=e.get("T")
            direction={1807:"over",1806:"under"}.get(typ)
            try:
                line=float(e.get("P")); odds=float(e.get("C"))
            except (TypeError,ValueError): continue
            if not player or not direction or not math.isfinite(line) or not math.isfinite(odds) or line<0 or not 1.01<odds<=50: continue
            eid=str(event.get("I") or event.get("CI") or "")
            result.append({"source":"22bet_linefeed","bookmaker":"22bet","sport":"NBA","league":"NBA","source_event_id":eid,"event_id":eid,
                "commence_time":str(event.get("S") or ""),"home_team":str(event.get("O1") or ""),"away_team":str(event.get("O2") or ""),
                "player_name":player,"market":"points","market_key":"points","direction":direction,"line":line,"odds_decimal":odds,
                "selection":f"{player} {direction} {line} points","raw":{"host":host,"type":typ,"player_id":pl.get("I")}})
    return result
