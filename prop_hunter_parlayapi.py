#!/usr/bin/env python3
"""ParlayAPI player-prop adapter (optional free key)."""
from __future__ import annotations
import math, os, re
from typing import Any, Dict, List
import requests
API_BASE=os.getenv("PARLAY_API_BASE","https://parlay-api.com/v1").rstrip("/"); API_KEY=os.getenv("PARLAY_API_KEY","").strip(); TIMEOUT=max(3,min(10,int(os.getenv("PH_PARLAY_TIMEOUT","6")))); LIMIT=max(100,min(10000,int(os.getenv("PH_PARLAY_LIMIT","5000"))))
SPORT_KEYS={"MLB":"baseball_mlb","NBA":"basketball_nba","WNBA":"basketball_wnba","NFL":"americanfootball_nfl","NHL":"icehockey_nhl","NCAAB":"basketball_ncaab","NCAAF":"americanfootball_ncaaf"}
MARKETS={"MLB":["player_total_bases","player_hits","player_home_runs","player_rbis","player_runs","player_strikeouts"],"NBA":["player_points","player_rebounds","player_assists","player_threes","player_points_rebounds_assists"],"WNBA":["player_points","player_rebounds","player_assists","player_threes","player_points_rebounds_assists"],"NFL":["player_pass_yds","player_pass_tds","player_rush_yds","player_reception_yds","player_receptions","player_anytime_td"],"NHL":["player_points","player_goals","player_assists","player_shots_on_goal","player_goalie_saves"],"NCAAB":["player_points","player_rebounds","player_assists","player_threes"],"NCAAF":["player_pass_yds","player_pass_tds","player_rush_yds","player_reception_yds","player_receptions","player_anytime_td"]}
def configured(): return bool(API_KEY)
def _f(v):
    try:
        x=float(v); return x if math.isfinite(x) else None
    except Exception:return None
def _decimal(v):
    x=_f(v)
    if x is None or x==0:return None
    if x>=100:return round(1+x/100,4)
    if x<=-100:return round(1+100/abs(x),4)
    if 1.01<x<=50:return round(x,4)
    return None
def _novig(o,u):
    try:
        a,b=1/float(o),1/float(u); t=a+b; return (a/t,b/t) if t>0 else (None,None)
    except Exception:return (None,None)
def _norm(v):return re.sub(r"[^a-z0-9]+","_",str(v or "").lower()).strip("_") or "player_prop"
def _rows(p):
    if isinstance(p,list):return p
    if isinstance(p,dict):
        for k in ("data","props","items","results"):
            if isinstance(p.get(k),list):return p[k]
    return []
def parse_rows(payload:Any,sport:str)->List[Dict[str,Any]]:
    out=[]
    for item in _rows(payload):
        if not isinstance(item,dict):continue
        player=str(item.get("player") or item.get("player_name") or item.get("description") or "").strip(); market=_norm(item.get("market") or item.get("market_key") or item.get("key")); line=_f(item.get("line") if item.get("line") is not None else item.get("point"))
        if not player or line is None:continue
        over=_decimal(item.get("over_price") if item.get("over_price") is not None else item.get("over")); under=_decimal(item.get("under_price") if item.get("under_price") is not None else item.get("under"))
        if not over and not under:continue
        fo,fu=_novig(over,under) if over and under else (None,None); eid=str(item.get("event_id") or item.get("eventId") or item.get("id") or ""); book=str(item.get("bookmaker") or item.get("book") or item.get("source") or "parlayapi").lower(); start=str(item.get("commence_time") or item.get("start_time") or item.get("date") or ""); home=str(item.get("home_team") or item.get("home") or ""); away=str(item.get("away_team") or item.get("away") or "")
        for direction,price,fair in (("over",over,fo),("under",under,fu)):
            if not price:continue
            out.append({"source":"parlayapi","bookmaker":book,"sport":sport,"league":sport,"source_event_id":eid,"event_id":eid,"commence_time":start,"home_team":home,"away_team":away,"player_name":player,"market":market,"market_key":market,"direction":direction,"line":float(line),"odds_decimal":price,"selection":direction.title(),"raw":{"paired_fair_prob":round(fair,6) if fair else None,"over_decimal":over,"under_decimal":under}})
    return out
def fetch_parlayapi_props(sport:str)->List[Dict[str,Any]]:
    sport=str(sport or "").upper(); sk=SPORT_KEYS.get(sport)
    if not API_KEY or not sk:return []
    params={"limit":LIMIT}; markets=MARKETS.get(sport)
    if markets:params["markets"]=",".join(markets)
    try:
        r=requests.get(f"{API_BASE}/sports/{sk}/props",params=params,headers={"X-API-Key":API_KEY,"Accept":"application/json","User-Agent":"PROP-HUNTER/13.10"},timeout=TIMEOUT)
        if r.status_code in (401,402,403,404,429):return []
        r.raise_for_status();return parse_rows(r.json(),sport)
    except Exception:return []
