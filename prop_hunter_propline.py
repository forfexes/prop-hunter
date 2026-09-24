#!/usr/bin/env python3
"""PropLine observed player-prop adapter.

One bounded bulk sport request where possible. Optional: no network call unless
PROPLINE_API_KEY is configured.
"""
from __future__ import annotations
import math, os, re
from typing import Any, Dict, List
import requests

API_BASE=os.getenv("PROPLINE_API_BASE","https://api.prop-line.com/v1").rstrip("/")
API_KEY=os.getenv("PROPLINE_API_KEY","").strip()
TIMEOUT=max(3,min(10,int(os.getenv("PH_PROPLINE_TIMEOUT","6"))))
SPORT_KEYS={"MLB":"baseball_mlb","NBA":"basketball_nba","WNBA":"basketball_wnba","NFL":"americanfootball_nfl","NHL":"icehockey_nhl","NCAAB":"basketball_ncaab","NCAAF":"americanfootball_ncaaf"}
MARKETS={
 "MLB":["batter_hits","batter_total_bases","batter_home_runs","batter_rbis","batter_runs_scored","pitcher_strikeouts"],
 "NBA":["player_points","player_rebounds","player_assists","player_threes","player_points_rebounds_assists"],
 "WNBA":["player_points","player_rebounds","player_assists","player_threes","player_points_rebounds_assists"],
 "NFL":["player_pass_yds","player_pass_tds","player_rush_yds","player_receptions","player_reception_yds","player_anytime_td"],
 "NHL":["player_points","player_goals","player_assists","player_shots_on_goal","player_goalie_saves"],
 "NCAAB":["player_points","player_rebounds","player_assists","player_threes"],
 "NCAAF":["player_pass_yds","player_pass_tds","player_rush_yds","player_receptions","player_reception_yds","player_anytime_td"],
}
def configured(): return bool(API_KEY)
def _f(v):
    try:
        x=float(v); return x if math.isfinite(x) else None
    except Exception: return None
def _decimal(v):
    x=_f(v)
    if x is None or x==0: return None
    if x>=100: return round(1+x/100,4)
    if x<=-100: return round(1+100/abs(x),4)
    if 1.01<x<=50: return round(x,4)
    return None
def _norm_market(v): return re.sub(r"[^a-z0-9]+","_",str(v or "").lower()).strip("_") or "player_prop"
def _events(payload):
    if isinstance(payload,list): return [x for x in payload if isinstance(x,dict)]
    if isinstance(payload,dict):
        for k in ("data","events","items"):
            if isinstance(payload.get(k),list): return [x for x in payload[k] if isinstance(x,dict)]
        if payload.get("bookmakers"): return [payload]
    return []
def parse_payload(payload: Any,sport: str)->List[Dict[str,Any]]:
    rows=[]
    for ev in _events(payload):
        eid=str(ev.get("id") or ev.get("event_id") or ev.get("eventId") or ""); home=str(ev.get("home_team") or ev.get("home") or ""); away=str(ev.get("away_team") or ev.get("away") or ""); start=str(ev.get("commence_time") or ev.get("start_time") or ev.get("date") or "")
        books=ev.get("bookmakers") or []
        if isinstance(books,dict): books=[{"key":k,**(v if isinstance(v,dict) else {"markets":v})} for k,v in books.items()]
        for book in books if isinstance(books,list) else []:
            if not isinstance(book,dict): continue
            bk=str(book.get("key") or book.get("name") or "propline").lower(); markets=book.get("markets") or []
            if isinstance(markets,dict): markets=[{"key":k,"outcomes":v} for k,v in markets.items()]
            for market in markets if isinstance(markets,list) else []:
                if not isinstance(market,dict): continue
                mk=_norm_market(market.get("key") or market.get("name"))
                for out in market.get("outcomes") or []:
                    if not isinstance(out,dict): continue
                    name=str(out.get("name") or out.get("side") or "").lower(); direction="under" if name in {"under","no"} or "under" in name else "over" if name in {"over","yes"} or "over" in name else ""
                    if not direction: continue
                    player=str(out.get("description") or out.get("player_name") or out.get("player") or "").strip(); line=_f(out.get("point") if out.get("point") is not None else out.get("line"))
                    if line is None and name in {"yes","no"}: line=.5
                    price=_decimal(out.get("price") if out.get("price") is not None else out.get("odds"))
                    if not player or line is None or not price: continue
                    rows.append({"source":"propline","bookmaker":bk,"sport":sport,"league":sport,"source_event_id":eid,"event_id":eid,"commence_time":start,"home_team":home,"away_team":away,"player_name":player,"market":mk,"market_key":mk,"direction":direction,"line":float(line),"odds_decimal":price,"selection":str(out.get("name") or direction.title()),"raw":{"resolution":out.get("resolution"),"actual_value":out.get("actual_value")}})
    return rows
def fetch_propline_props(sport: str)->List[Dict[str,Any]]:
    sport=str(sport or "").upper(); sk=SPORT_KEYS.get(sport)
    if not API_KEY or not sk: return []
    try:
        r=requests.get(f"{API_BASE}/sports/{sk}/odds",params={"markets":",".join(MARKETS.get(sport,[]))},headers={"X-API-Key":API_KEY,"Accept":"application/json","User-Agent":"PROP-HUNTER/13.10"},timeout=TIMEOUT)
        if r.status_code in (401,402,403,404,429): return []
        r.raise_for_status(); return parse_payload(r.json(),sport)
    except Exception: return []
