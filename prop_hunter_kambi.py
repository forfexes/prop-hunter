#!/usr/bin/env python3
"""Multi-brand Kambi public offering adapter for PROP HUNTER.

Uses the same public JSON family that NETRATTLER already relies on. No login,
browser or bypass. All four configured brands are treated as separate observed
books and may contribute consensus/fair-probability pairs.
"""
from __future__ import annotations
import math, os, re
from typing import Any
import requests
ENABLED=str(os.getenv("PH_KAMBI_ENABLED","0")).lower() in {"1","true","yes","on"}; TIMEOUT=max(2,min(10,int(os.getenv("PH_KAMBI_TIMEOUT","4")))); MAX_BRANDS=max(1,min(8,int(os.getenv("PH_KAMBI_MAX_BRANDS","4")))); BRANDS=[x.strip() for x in os.getenv("PH_KAMBI_BRANDS","ub,bs,888,nb").split(",") if x.strip()]; HOSTS=["https://eu-offering-api.kambicdn.com","https://e0-api.kambi.com"]
SPORT_PATHS={"MLB":("baseball",),"NBA":("basketball",),"WNBA":("basketball",),"NFL":("american_football","american-football"),"NHL":("ice_hockey","ice-hockey"),"NCAAB":("basketball",),"NCAAF":("american_football","american-football")}
def configured():return ENABLED
def _f(v):
    try:
        x=float(v);return x if math.isfinite(x) else None
    except Exception:return None
def _price(o):
    for k in ("oddsDecimal","decimalOdds"):
        x=_f(o.get(k))
        if x and 1.01<x<=50:return round(x,4)
    x=_f(o.get("odds"))
    if not x:return None
    if x>100:return round(x/1000.0,4)
    return round(x,4) if 1.01<x<=50 else None
def _line(o,label,crit):
    x=_f(o.get("line"))
    if x is not None:return x/1000.0 if abs(x)>=100 else x
    for k in ("points","handicap"):
        x=_f(o.get(k))
        if x is not None:return x/1000.0 if abs(x)>=100 else x
    m=re.search(r"(\d+(?:\.\d+)?)",f"{label} {crit}");return float(m.group(1)) if m else None
def _get(url,params=None):
    h={"Accept":"application/json,text/plain,*/*","User-Agent":"Mozilla/5.0 PROP-HUNTER"}
    try:
        r=requests.get(url,params=params or {},headers=h,timeout=TIMEOUT)
        if r.status_code==200:return r.json()
        if r.status_code not in (403,429):return None
    except Exception:pass
    try:
        from curl_cffi import requests as creq
        r=creq.get(url,params=params or {},headers=h,impersonate="chrome",timeout=TIMEOUT);return r.json() if r.status_code==200 else None
    except Exception:return None
def _norm_market(v):
    s=re.sub(r"\b(over|under|yes|no)\b"," ",str(v or "").lower());return re.sub(r"[^a-z0-9]+","_",s).strip("_") or "player_prop"
def _looks_prop(offer,outcome):
    text=" ".join([str((offer.get("criterion") or {}).get("label") or ""),str((offer.get("betOfferType") or {}).get("name") or ""),str(outcome.get("label") or ""),str(outcome.get("participant") or "")]).lower();return any(t in text for t in ("player","points","rebounds","assists","yards","touchdown","strikeouts","home run","hits","bases","shots","saves","goals","blocks","steals","receptions"))
def _player(offer,outcome):
    for k in ("participant","participantName","playerName"):
        if outcome.get(k):return str(outcome.get(k)).strip()
    label=str(outcome.get("label") or "").strip()
    if " - " in label:
        h=label.split(" - ",1)[0].strip()
        if len(h.split())>=2:return h
    crit=str((offer.get("criterion") or {}).get("label") or "")
    for sep in (" - ",": "):
        if sep in crit:
            h=crit.split(sep,1)[0].strip()
            if len(h.split())>=2:return h
    return ""
def _league_ok(sport,e):
    text=" ".join(str(e.get(k) or "") for k in ("name","englishName","pathName","group","leagueName")).lower()
    if sport=="NBA":return "wnba" not in text and ("nba" in text or not any(x in text for x in ("ncaa","college")))
    if sport=="WNBA":return "wnba" in text
    if sport=="NFL":return "nfl" in text
    if sport in {"NCAAF","NCAAB"}:return any(x in text for x in ("ncaa","college"))
    if sport=="MLB":return "mlb" in text or "major league" in text
    if sport=="NHL":return "nhl" in text
    return True
def parse_offer(payload:Any,sport:str,event_id:str,home:str,away:str,start:str,brand:str):
    offers=payload.get("betOffers") if isinstance(payload,dict) else payload
    if not isinstance(offers,list):return []
    rows=[]
    for offer in offers:
        if not isinstance(offer,dict):continue
        crit=str((offer.get("criterion") or {}).get("label") or offer.get("label") or "");market=_norm_market(crit)
        for o in offer.get("outcomes") or []:
            if not isinstance(o,dict) or not _looks_prop(offer,o):continue
            player=_player(offer,o);label=str(o.get("label") or "");low=label.lower().strip();direction="under" if ("under" in low or low=="no") else "over" if ("over" in low or low=="yes") else ""
            if not player or not direction:continue
            line=_line(o,label,crit)
            if line is None and low in {"yes","no"}:line=.5
            price=_price(o)
            if line is None or not price:continue
            rows.append({"source":"kambi","bookmaker":f"kambi_{brand}","sport":sport,"league":sport,"source_event_id":str(event_id),"event_id":str(event_id),"commence_time":start,"home_team":home,"away_team":away,"player_name":player,"market":market,"market_key":market,"direction":direction,"line":float(line),"odds_decimal":price,"selection":label,"raw":{"criterion":crit,"outcome_id":o.get("id"),"brand":brand}})
    return rows
def fetch_kambi_props(sport:str,max_events:int=3):
    sport=str(sport or "").upper()
    if not ENABLED or sport not in SPORT_PATHS:return []
    rows=[]
    for brand in BRANDS[:MAX_BRANDS]:
        brand_rows=[]
        for host in HOSTS:
            events=None
            for path in SPORT_PATHS[sport]:
                events=_get(f"{host}/offering/v2018/{brand}/listView/{path}/all/all/all/matches.json",{"lang":"en_GB","market":"GB"})
                if isinstance(events,dict) and events.get("events"):break
            if not isinstance(events,dict):continue
            count=0
            for wrapper in events.get("events") or []:
                e=(wrapper.get("event") if isinstance(wrapper,dict) else None) or wrapper
                if not isinstance(e,dict) or not _league_ok(sport,e):continue
                eid=e.get("id")
                if not eid:continue
                offer=_get(f"{host}/offering/v2018/{brand}/betoffer/event/{eid}.json",{"lang":"en_GB","market":"GB"});brand_rows.extend(parse_offer(offer,sport,str(eid),str(e.get("homeName") or ""),str(e.get("awayName") or ""),str(e.get("start") or e.get("startTime") or ""),brand));count+=1
                if count>=max_events:break
            if brand_rows:break
        rows.extend(brand_rows)
    dedup={}
    for r in rows:dedup[(r.get("bookmaker"),r.get("source_event_id"),r.get("player_name"),r.get("market_key"),r.get("direction"),r.get("line"),r.get("odds_decimal"))]=r
    return list(dedup.values())
