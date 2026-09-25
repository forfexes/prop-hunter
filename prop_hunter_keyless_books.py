#!/usr/bin/env python3
"""Keyless direct sportsbook player-prop feeds for PROP HUNTER.

Patterns are based on public sportsbook JSON and the MIT-described oddswrap
project. No login, account, CAPTCHA, proxy, geo bypass or browser automation.
Only observed prices survive the central quote guard.
"""
from __future__ import annotations
import math, os, re, time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import requests
from prop_hunter_quote_guard import sanitize_row

ENABLED=str(os.getenv("PH_KEYLESS_BOOKS_ENABLED","1")).lower() in {"1","true","yes","on"}
TIMEOUT=max(2,min(10,int(os.getenv("PH_KEYLESS_TIMEOUT","5"))))
MAX_EVENTS=max(1,min(8,int(os.getenv("PH_KEYLESS_MAX_EVENTS","3"))))
MAX_CATEGORIES=max(1,min(12,int(os.getenv("PH_KEYLESS_MAX_PROP_CATEGORIES","6"))))
TTL=max(60,min(3600,int(os.getenv("PH_KEYLESS_CACHE_TTL","600"))))
SOURCE_BUDGET=max(5,min(60,int(os.getenv("PH_KEYLESS_SOURCE_BUDGET_SEC","20"))))
BOOKS={x.strip().lower() for x in os.getenv("PH_KEYLESS_BOOKS","draftkings,fanduel,bovada,betrivers").split(",") if x.strip()}
CACHE:Dict[str,Tuple[float,Any]]={}
HEADERS={"Accept":"application/json,text/plain,*/*","User-Agent":"Mozilla/5.0 PROP-HUNTER/13.10.1"}

def configured(): return ENABLED and bool(BOOKS)
def _f(v):
    try:
        x=float(str(v).replace("−","-").replace("+","").strip()); return x if math.isfinite(x) else None
    except Exception:return None
def _dec(v):
    x=_f(v)
    if x is None or x==0:return None
    if 1.001<x<50:return round(x,4)
    if x>=100:return round(1+x/100,4)
    if x<=-100:return round(1+100/abs(x),4)
def _get(url,params=None):
    key=f"{url}|{sorted((params or {}).items())}"; old=CACHE.get(key)
    if old and time.time()-old[0]<TTL:return old[1]
    data=None
    try:
        r=requests.get(url,params=params or {},headers=HEADERS,timeout=TIMEOUT)
        if r.status_code==200:data=r.json()
        elif r.status_code not in {403,406,429}:CACHE[key]=(time.time(),None);return None
    except Exception:pass
    if data is None:
        try:
            from curl_cffi import requests as creq
            r=creq.get(url,params=params or {},headers=HEADERS,impersonate="chrome120",timeout=TIMEOUT)
            if r.status_code==200:data=r.json()
        except Exception:pass
    CACHE[key]=(time.time(),data); return data
def _norm(v):return re.sub(r"[^a-z0-9]+"," ",str(v or "").lower()).strip()
def _mk(v):
    s=_norm(v); rules=[
      (("points rebounds assists","points rebounds and assists","pra"),"pra"),(("total bases",),"total_bases"),
      (("home run","home runs"),"home_runs"),(("pitcher strikeout","pitcher strikeouts"),"pitcher_strikeouts"),
      (("stolen base","stolen bases"),"stolen_bases"),(("passing touchdown","pass td"),"passing_touchdowns"),
      (("passing yards","pass yds"),"passing_yards"),(("rushing yards","rush yds"),"rushing_yards"),
      (("receiving yards","reception yards"),"receiving_yards"),(("receptions",),"receptions"),
      (("anytime td","anytime touchdown","touchdown scorer"),"anytime_td"),(("shots on goal",),"shots_on_goal"),
      (("goalie saves",),"goalie_saves"),(("three pointers","3 pointers","3pm","threes"),"threes"),
      (("rebounds",),"rebounds"),(("assists",),"assists"),(("points",),"points"),(("hits",),"hits"),
      (("rbi","rbis"),"rbi"),(("goals",),"goals"),(("runs",),"runs"),(("blocks",),"blocks"),(("steals",),"steals")]
    for needles,out in rules:
        if any(n in s for n in needles):return out
    return re.sub(r"[^a-z0-9]+","_",s).strip("_") or "player_prop"
SUFFIXES=("points rebounds assists","points rebounds and assists","total bases","home runs","home run","pitcher strikeouts","strikeouts","stolen bases","stolen base","passing touchdowns","passing touchdown","passing yards","rushing yards","receiving yards","receptions","anytime touchdown","anytime td","shots on goal","goalie saves","three pointers","3 pointers","rebounds","assists","points","hits","rbi","rbis","runs","goals","blocks","steals")
def _player_market(text):
    raw=re.sub(r"\s+O/U\s*$","",str(text or ""),flags=re.I).strip(); low=raw.lower()
    for x in sorted(SUFFIXES,key=len,reverse=True):
        if low.endswith(" "+x):return raw[:-(len(x)+1)].strip(" -–—:")
    return ""
def _game(name):
    t=str(name or "")
    for sep in (" @ "," vs "," v "):
        if sep in t:
            a,h=t.split(sep,1);return a.strip(),h.strip()
    return "",""
def _iso(ms):
    try:return datetime.fromtimestamp(float(ms)/1000,tz=timezone.utc).isoformat()
    except Exception:return str(ms or "")
def _safe(row):
    try:return sanitize_row(row)
    except Exception:return None

DK_LEAGUES={"MLB":84240,"NBA":42648,"NFL":88808,"NHL":42133}
DK_BASE="https://sportsbook-nash.draftkings.com/api/sportscontent/dkusnj/v1"
DK_HINTS=("player","batter","pitcher","hits","bases","home run","rbi","strikeout","stolen","points","rebounds","assists","three","passing","rushing","receiving","receptions","touchdown","shots","saves","goals","blocks","steals")
def parse_draftkings_payload(p,sport):
    if not isinstance(p,dict):return []
    evs={str(e.get("id")):e for e in p.get("events",[]) if isinstance(e,dict)}; sels={}
    for x in p.get("selections",[]) or []:
        if isinstance(x,dict):sels.setdefault(str(x.get("marketId") or ""),[]).append(x)
    out=[]
    for m in p.get("markets",[]) or []:
        if not isinstance(m,dict):continue
        mid,eid=str(m.get("id") or ""),str(m.get("eventId") or ""); name=str(m.get("name") or ""); player=_player_market(name)
        if not player:continue
        mk=_mk(name); ev=evs.get(eid,{}); away,home=_game(ev.get("name")); start=str(ev.get("startEventDate") or ev.get("startDate") or ""); ms=sels.get(mid,[])
        threshold=False
        for x in ms:
            lab=str(x.get("label") or "").strip(); mm=re.fullmatch(r"(\d+)\+",lab)
            if not mm:continue
            threshold=True; price=_dec((x.get("displayOdds") or {}).get("american")); n=int(mm.group(1))
            row=_safe({"source":"draftkings_direct","bookmaker":"draftkings","sport":sport,"league":sport,"source_event_id":eid,"event_id":eid,"commence_time":start,"home_team":home,"away_team":away,"player_name":player,"market":mk,"market_key":mk,"direction":"over","line":max(.5,n-.5),"odds_decimal":price,"selection":lab,"raw":{"market_name":name,"threshold":n}})
            if row:out.append(row)
        if threshold:continue
        for x in ms:
            lab=str(x.get("label") or ""); low=lab.lower(); side="over" if low.startswith("over") else "under" if low.startswith("under") else ""
            if not side:continue
            line=_f(x.get("points")); mm=re.search(r"(\d+(?:\.\d+)?)",lab); line=line if line is not None else (float(mm.group(1)) if mm else None)
            row=_safe({"source":"draftkings_direct","bookmaker":"draftkings","sport":sport,"league":sport,"source_event_id":eid,"event_id":eid,"commence_time":start,"home_team":home,"away_team":away,"player_name":player,"market":mk,"market_key":mk,"direction":side,"line":line,"odds_decimal":_dec((x.get("displayOdds") or {}).get("american")),"selection":lab,"raw":{"market_name":name}})
            if row:out.append(row)
    return out
def fetch_draftkings_props(sport):
    sport=str(sport or "").upper(); lid=DK_LEAGUES.get(sport)
    if not ENABLED or "draftkings" not in BOOKS or not lid:return []
    started=time.monotonic(); root=_get(f"{DK_BASE}/leagues/{lid}")
    if not isinstance(root,dict):return []
    cats={str(x.get("id")):str(x.get("name") or "") for x in root.get("categories",[]) if isinstance(x,dict)}; candidates=[]
    for sc in root.get("subcategories",[]) or []:
        if not isinstance(sc,dict):continue
        cid,sid=str(sc.get("categoryId") or ""),str(sc.get("id") or ""); text=f"{cats.get(cid,'')} {sc.get('name') or ''}".lower()
        if cid and sid and any(h in text for h in DK_HINTS):candidates.append((cid,sid))
    out=[]
    for cid,sid in list(dict.fromkeys(candidates))[:MAX_CATEGORIES]:
        if time.monotonic()-started>SOURCE_BUDGET:break
        out+=parse_draftkings_payload(_get(f"{DK_BASE}/leagues/{lid}/categories/{cid}/subcategories/{sid}"),sport)
    return out

FD_IDS={"MLB":"mlb","NBA":"nba","WNBA":"wnba","NFL":"nfl","NHL":"nhl"}; FD_AK="FhMFpcPWXMeyZxOx"
FD_BASE="https://sbapi.nj.sportsbook.fanduel.com/api/content-managed-page"; FD_EVENT="https://sbapi.nj.sportsbook.fanduel.com/api/event-page"
def _fd_line(name):
    m=re.search(r"(\d+)\+",str(name or ""))
    if m:return max(.5,int(m.group(1))-.5)
    return .5 if re.search(r"\b(?:a|an)\b",str(name or ""),re.I) else None
def parse_fanduel_event_page(page,sport,event=None):
    if not isinstance(page,dict):return []
    event=event or {}; eid=str(event.get("eventId") or event.get("id") or ""); away,home=_game(event.get("name")); away=away.split(" (")[0].strip();home=home.split(" (")[0].strip();start=str(event.get("openDate") or event.get("startTime") or "")
    markets=(page.get("attachments") or {}).get("markets") or {}; markets=markets.values() if isinstance(markets,dict) else markets if isinstance(markets,list) else [] ; out=[]
    for m in markets:
        if not isinstance(m,dict):continue
        runners=m.get("runners") or []
        if not any(isinstance(r,dict) and r.get("isPlayerSelection") for r in runners):continue
        name=str(m.get("marketName") or ""); mk=_mk(name); threshold=_fd_line(name)
        for r in runners:
            if not isinstance(r,dict) or not r.get("isPlayerSelection"):continue
            rn=str(r.get("runnerName") or "").strip(); line=_f(r.get("handicap")); side="over"; player=rn
            if threshold is not None:line=line if line is not None else threshold
            else:
                sm=re.search(r"\b(over|under)\b",rn,re.I)
                if not sm:continue
                side=sm.group(1).lower(); player=re.sub(r"\s*[-–—:]?\s*\b(?:over|under)\b.*$","",rn,flags=re.I).strip()
                if line is None:
                    lm=re.search(r"(\d+(?:\.\d+)?)",rn[sm.end():]);line=float(lm.group(1)) if lm else None
            amer=((r.get("winRunnerOdds") or {}).get("americanDisplayOdds") or {}).get("americanOdds")
            row=_safe({"source":"fanduel_direct","bookmaker":"fanduel","sport":sport,"league":sport,"source_event_id":eid,"event_id":eid,"commence_time":start,"home_team":home,"away_team":away,"player_name":player,"market":mk,"market_key":mk,"direction":side,"line":line,"odds_decimal":_dec(amer),"selection":name,"raw":{"market_name":name}})
            if row:out.append(row)
    return out
def fetch_fanduel_props(sport):
    sport=str(sport or "").upper(); pageid=FD_IDS.get(sport)
    if not ENABLED or "fanduel" not in BOOKS or not pageid:return []
    started=time.monotonic(); root=_get(FD_BASE,{"page":"CUSTOM","customPageId":pageid,"_ak":FD_AK}); evs=(root or {}).get("attachments",{}).get("events",{}) if isinstance(root,dict) else {}
    if not isinstance(evs,dict):return []
    out=[]
    for eid,ev in [(str(k),v) for k,v in evs.items() if isinstance(v,dict) and " @ " in str(v.get("name") or "")][:MAX_EVENTS]:
        if time.monotonic()-started>SOURCE_BUDGET:break
        e=dict(ev);e.setdefault("eventId",eid);out+=parse_fanduel_event_page(_get(FD_EVENT,{"eventId":eid,"tab":"popular","_ak":FD_AK}),sport,e)
    return out

BOV_PATH={"MLB":"baseball/mlb","NBA":"basketball/nba","WNBA":"basketball/wnba","NFL":"football/nfl","NHL":"hockey/nhl","NCAAF":"football/college-football","NCAAB":"basketball/college-basketball"}
BOV_URL="https://www.bovada.lv/services/sports/event/coupon/events/A/description/{path}"
def parse_bovada_events(events,sport):
    if not isinstance(events,list):return []
    out=[]
    for ev in events:
        if not isinstance(ev,dict) or ev.get("live") is True:continue
        eid=str(ev.get("id") or "");home=away=""
        for c in ev.get("competitors") or []:
            if isinstance(c,dict):
                if c.get("home"):home=str(c.get("name") or "")
                else:away=str(c.get("name") or "")
        if not(home or away):away,home=_game(ev.get("description"))
        for dg in ev.get("displayGroups") or []:
            if not isinstance(dg,dict) or str(dg.get("description") or "").lower()=="game lines":continue
            for m in dg.get("markets") or []:
                desc=str(m.get("description") or "") if isinstance(m,dict) else ""
                if " - " not in desc:continue
                base,player=desc.split(" - ",1);player=re.sub(r"\s*\([^)]*\)\s*$","",player).strip();mk=_mk(base)
                for o in m.get("outcomes") or []:
                    lab=str(o.get("description") or "");low=lab.lower();side="over" if low=="yes" or low.startswith("over") else "under" if low=="no" or low.startswith("under") else ""
                    if not side:continue
                    price=o.get("price") or {}; row=_safe({"source":"bovada_direct","bookmaker":"bovada","sport":sport,"league":sport,"source_event_id":eid,"event_id":eid,"commence_time":_iso(ev.get("startTime")),"home_team":home,"away_team":away,"player_name":player,"market":mk,"market_key":mk,"direction":side,"line":_f(price.get("handicap")) if isinstance(price,dict) else None,"odds_decimal":_dec(price.get("american")) if isinstance(price,dict) else None,"selection":lab,"raw":{"market_name":desc}})
                    if row:out.append(row)
    return out
def fetch_bovada_props(sport):
    sport=str(sport or "").upper();path=BOV_PATH.get(sport)
    if not ENABLED or "bovada" not in BOOKS or not path:return []
    p=_get(BOV_URL.format(path=path),{"lang":"en","preMatchOnly":"true"}); events=(p[0].get("events") or []) if isinstance(p,list) and p and isinstance(p[0],dict) else (p.get("events") or []) if isinstance(p,dict) else []
    return parse_bovada_events(events,sport)

BR_PATH={"MLB":"baseball/mlb","NBA":"basketball/nba","WNBA":"basketball/wnba","NFL":"american_football/nfl","NHL":"ice_hockey/nhl","NCAAF":"american_football/ncaaf","NCAAB":"basketball/ncaab"};BR_BASE="https://eu-offering-api.kambicdn.com/offering/v2018/rsiusnj"
def fetch_betrivers_props(sport):
    sport=str(sport or "").upper();path=BR_PATH.get(sport)
    if not ENABLED or "betrivers" not in BOOKS or not path:return []
    listing=_get(f"{BR_BASE}/listView/{path}/all/all/matches.json",{"lang":"en_US","market":"US"});events=listing.get("events") if isinstance(listing,dict) else None
    if not isinstance(events,list):return []
    from prop_hunter_kambi import parse_offer
    started=time.monotonic();out=[]
    for wrap in events[:MAX_EVENTS]:
        if time.monotonic()-started>SOURCE_BUDGET:break
        e=(wrap.get("event") if isinstance(wrap,dict) else None) or wrap
        if not isinstance(e,dict) or not e.get("id"):continue
        eid=str(e["id"]); rows=parse_offer(_get(f"{BR_BASE}/betoffer/event/{eid}.json",{"lang":"en_US","market":"US"}),sport,eid,str(e.get("homeName") or ""),str(e.get("awayName") or ""),str(e.get("start") or e.get("startTime") or ""),"betrivers")
        for row in rows:
            row=dict(row);row["source"]="betrivers_direct";row["bookmaker"]="betrivers";safe=_safe(row)
            if safe:out.append(safe)
    return out

def fetch_all_keyless(sport):
    out=[]
    for fn in (fetch_draftkings_props,fetch_fanduel_props,fetch_bovada_props,fetch_betrivers_props):
        try:out+=fn(sport) or []
        except Exception:pass
    return out
