#!/usr/bin/env python3
"""Lossless, non-publishing 22bet player market candidate extraction.

Numeric G/T identifiers are deliberately not translated to named markets.
"""
from __future__ import annotations
import math

def extract_candidates(payload, *, league, event_id, subgame_title):
    val=payload.get("Value") if isinstance(payload,dict) else None
    if not isinstance(val,dict):return []
    rows=[]
    for group in val.get("GE") or []:
        if not isinstance(group,dict):continue
        for bucket in group.get("E") or []:
            for item in (bucket if isinstance(bucket,list) else [bucket]):
                if not isinstance(item,dict):continue
                player=item.get("PL")
                if not isinstance(player,dict) or not str(player.get("N") or "").strip():continue
                try: price=float(item["C"])
                except (TypeError,ValueError,KeyError):continue
                if not math.isfinite(price) or not 1.0<price<=1000:continue
                rawline=item.get("P")
                try: line=float(rawline) if rawline is not None else None
                except (TypeError,ValueError):line=None
                if line is not None and not math.isfinite(line):continue
                rows.append({"league":league,"event_id":str(event_id),"subgame_title":subgame_title,
                             "player":str(player["N"]).strip(),"player_id":player.get("I"),
                             "group_id":group.get("G"),"type_id":item.get("T"),
                             "line":line,"odds_decimal":price,"market_verified":False})
    return rows
