#!/usr/bin/env python3
"""Observed event-market support for PROP HUNTER SGPs.

Adds alternate totals, alternate spreads/handicaps and both-teams-100+ style
basketball game legs from direct sportsbook JSON. No line or price is invented.
"""
from __future__ import annotations
import re
from typing import Any, Dict, List


def _norm(v: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(v or "").lower()).strip()


def event_market_key(value: Any) -> str:
    s=_norm(value)
    if not s:return ""
    if "both teams" in s and ("100" in s or "score" in s):return "both_teams_100_points"
    if "alternate total" in s or "alt total" in s:return "alternate_total_points"
    if ("total points" in s or "game total" in s or s in {"total","totals"}) and "player" not in s:return "game_total_points"
    if "alternate handicap" in s or "alt handicap" in s or "alternate spread" in s or "alt spread" in s:return "alternate_spread"
    if "point spread" in s or s=="spread" or s.endswith(" spread"):return "point_spread"
    return ""


def _dec(kb, runner):
    odds=runner.get("displayOdds") or runner.get("winRunnerOdds") or {}
    amer=None
    if isinstance(odds,dict):
        amer=odds.get("american")
        if amer is None:amer=(odds.get("americanDisplayOdds") or {}).get("americanOdds")
    if amer is None:amer=runner.get("americanOdds") or runner.get("price")
    try:return kb._dec(amer)
    except Exception:return None


def _side_line(kb,label,runner,key):
    low=str(label or "").lower()
    side="over" if any(x in low for x in ("over","yes")) else "under" if any(x in low for x in ("under","no")) else ""
    line=kb._f(runner.get("points") if runner.get("points") is not None else runner.get("handicap"))
    if key=="both_teams_100_points":
        side=side or "over";line=.5 if line is None else line
    if line is None:
        m=re.search(r"([+-]?\d+(?:\.\d+)?)",str(label or ""));line=float(m.group(1)) if m else None
    return side,line


def _row(kb,source,book,sport,eid,start,home,away,key,side,line,price,selection,market_name):
    if not side or line is None or price is None:return None
    row={"source":source,"bookmaker":book,"sport":sport,"league":sport,"source_event_id":eid,"event_id":eid,
         "commence_time":start,"home_team":home,"away_team":away,"player_name":"GAME","market":key,"market_key":key,
         "direction":side,"line":line,"odds_decimal":price,"selection":selection,
         "raw":{"market_name":market_name,"event_market":True}}
    try:return kb._safe(row)
    except Exception:return None


def parse_draftkings_event_markets(kb,payload,sport)->List[Dict[str,Any]]:
    if not isinstance(payload,dict):return []
    evs={str(e.get("id")):e for e in payload.get("events",[]) if isinstance(e,dict)};sels={}
    for x in payload.get("selections",[]) or []:
        if isinstance(x,dict):sels.setdefault(str(x.get("marketId") or ""),[]).append(x)
    out=[]
    for m in payload.get("markets",[]) or []:
        if not isinstance(m,dict):continue
        name=str(m.get("name") or "");key=event_market_key(name)
        if not key:continue
        eid=str(m.get("eventId") or "");ev=evs.get(eid,{});away,home=kb._game(ev.get("name"));start=str(ev.get("startEventDate") or ev.get("startDate") or "")
        for x in sels.get(str(m.get("id") or ""),[]):
            label=str(x.get("label") or "");side,line=_side_line(kb,label,x,key)
            r=_row(kb,"draftkings_direct","draftkings",sport,eid,start,home,away,key,side,line,_dec(kb,x),label,name)
            if r:out.append(r)
    return out


def parse_fanduel_event_markets(kb,page,sport,event=None)->List[Dict[str,Any]]:
    if not isinstance(page,dict):return []
    event=event or {};eid=str(event.get("eventId") or event.get("id") or "");away,home=kb._game(event.get("name"));away=away.split(" (")[0].strip();home=home.split(" (")[0].strip();start=str(event.get("openDate") or event.get("startTime") or "")
    markets=(page.get("attachments") or {}).get("markets") or {};markets=markets.values() if isinstance(markets,dict) else markets if isinstance(markets,list) else []
    out=[]
    for m in markets:
        if not isinstance(m,dict):continue
        name=str(m.get("marketName") or "");key=event_market_key(name)
        if not key:continue
        for x in m.get("runners") or []:
            if not isinstance(x,dict):continue
            label=str(x.get("runnerName") or x.get("selectionName") or "");side,line=_side_line(kb,label,x,key)
            r=_row(kb,"fanduel_direct","fanduel",sport,eid,start,home,away,key,side,line,_dec(kb,x),label,name)
            if r:out.append(r)
    return out


def install(kb):
    if getattr(kb,"_ph_event_markets_installed",False):return kb
    old_dk=kb.parse_draftkings_payload;old_fd=kb.parse_fanduel_event_page
    def dk(payload,sport):
        rows=list(old_dk(payload,sport) or []);rows.extend(parse_draftkings_event_markets(kb,payload,sport));return rows
    def fd(page,sport,event=None):
        rows=list(old_fd(page,sport,event) or []);rows.extend(parse_fanduel_event_markets(kb,page,sport,event));return rows
    kb.parse_draftkings_payload=dk;kb.parse_fanduel_event_page=fd;kb._ph_event_markets_installed=True
    return kb
