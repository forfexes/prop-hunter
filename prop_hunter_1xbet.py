#!/usr/bin/env python3
"""Keyless 1xBet-family LineFeed adapter for PROP HUNTER.

Uses the same public JSON family proven useful in NETRATTLER, but with current
regional gateway variants and US-sport ids. It is best-effort and bounded:
no login, proxy, browser, CAPTCHA or geo bypass.
"""
from __future__ import annotations

import math
import os
import re
from typing import Any, Dict, Iterable, List, Optional

import requests

ENABLED = str(os.getenv("PH_1XBET_ENABLED", "1")).lower() in {"1","true","yes","on"}
TIMEOUT = max(2, min(8, int(os.getenv("PH_1XBET_TIMEOUT", "4"))))
MAX_EVENTS = max(1, min(5, int(os.getenv("PH_1XBET_MAX_EVENTS", "2"))))
HOSTS = [x.strip().rstrip("/") for x in os.getenv(
    "PH_1XBET_HOSTS",
    "https://1xbet.ng/service-api/LineFeed,https://1xbet.co.ke/service-api/LineFeed,https://1xbet.ug/service-api/LineFeed",
).split(",") if x.strip()]

SPORT_IDS = {
    "NHL": 2,
    "NBA": 3, "WNBA": 3, "NCAAB": 3,
    "MLB": 5,
    "NFL": 13, "NCAAF": 13,
}

def configured() -> bool:
    return ENABLED

def _f(v: Any) -> Optional[float]:
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None

def _norm(s: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()

def _league_ok(sport: str, row: Dict[str, Any]) -> bool:
    text = " ".join(str(row.get(k) or "") for k in ("LE","L","League","O1","O2","HomeTeam","AwayTeam")).lower()
    if sport == "NBA": return "nba" in text and "wnba" not in text
    if sport == "WNBA": return "wnba" in text
    if sport == "MLB": return "mlb" in text or "major league" in text
    if sport == "NFL": return "nfl" in text and "ncaa" not in text
    if sport == "NHL": return "nhl" in text
    if sport == "NCAAB": return any(x in text for x in ("ncaa","college","ncaab"))
    if sport == "NCAAF": return any(x in text for x in ("ncaa","college","ncaaf"))
    return True

def _get_json(url: str) -> Any:
    try:
        r=requests.get(url, headers={"Accept":"application/json,text/plain,*/*","User-Agent":"Mozilla/5.0 PROP-HUNTER"}, timeout=TIMEOUT)
        if r.status_code == 200:
            return r.json()
        if r.status_code not in (403,406,429):
            return None
    except Exception:
        pass
    try:
        from curl_cffi import requests as creq
        r=creq.get(url, headers={"Accept":"application/json,text/plain,*/*","User-Agent":"Mozilla/5.0"}, impersonate="chrome", timeout=TIMEOUT)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None

def _list_events(host: str, sport_id: int) -> List[Dict[str, Any]]:
    variants = (
        f"{host}/Get1x2_Zip?sports={sport_id}&count=80&lng=en&partner=159&getEmpty=true&gr=412&mode=3",
        f"{host}/Get1x2_VZip?sports={sport_id}&count=80&lng=en&mode=4&country=1&partner=159&getEmpty=true",
    )
    for url in variants:
        payload=_get_json(url)
        rows=(payload or {}).get("Value") if isinstance(payload,dict) else None
        if isinstance(rows,list) and rows:
            return rows
    return []

def _game(host: str, event_id: Any) -> Any:
    variants = (
        f"{host}/GetGameZip?id={event_id}&lng=en&partner=159&isSubGames=true&GroupEvents=true&allEventsGroupSubGames=true&countevents=250&grMode=2&marketType=1",
        f"{host}/GetGameZip?id={event_id}&lng=en&partner=159",
    )
    for url in variants:
        payload=_get_json(url)
        if isinstance(payload,dict) and payload.get("Value"):
            return payload
    return None

def _groups(value: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    for key in ("GE","Groups","groups"):
        groups=value.get(key)
        if isinstance(groups,list):
            for g in groups:
                if isinstance(g,dict):
                    yield g

def _outcomes(group: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    raw=group.get("E") or group.get("events") or group.get("outcomes") or []
    for item in raw:
        if isinstance(item,list):
            for e in item:
                if isinstance(e,dict): yield e
        elif isinstance(item,dict):
            yield item

def _direction(e: Dict[str, Any]) -> str:
    label=" ".join(str(e.get(k) or "") for k in ("PL","N","Name","PN")).lower()
    if re.search(r"\b(under|lower|no)\b", label): return "under"
    if re.search(r"\b(over|higher|yes)\b", label): return "over"
    try:
        t=int(e.get("T"))
        if t in (10,12,2952,2954): return "under"
        if t in (9,11,2951,2953): return "over"
    except Exception:
        pass
    return ""

def _market(group: Dict[str, Any]) -> str:
    raw=str(group.get("GS") or group.get("Name") or group.get("name") or group.get("GN") or "player_prop")
    s=re.sub(r"[^a-z0-9]+","_",raw.lower()).strip("_")
    return s or "player_prop"

def _is_player_market(group: Dict[str, Any], e: Dict[str, Any]) -> bool:
    player=str(e.get("PN") or e.get("PlayerName") or "").strip()
    if not player: return False
    text=(" ".join(str(group.get(k) or "") for k in ("GS","Name","name","GN"))+" "+str(e.get("PL") or "")).lower()
    tokens=("player","points","rebounds","assists","yards","touchdown","td","receptions","strikeouts",
            "home run","hits","bases","shots","saves","goals","blocks","steals")
    return any(t in text for t in tokens)

def parse_game(payload: Any, sport: str, event: Dict[str, Any], host: str="1xbet") -> List[Dict[str, Any]]:
    value=(payload or {}).get("Value") if isinstance(payload,dict) else None
    if not isinstance(value,dict):
        return []
    eid=str(event.get("I") or event.get("CI") or event.get("id") or "")
    home=str(event.get("O1") or event.get("HomeTeam") or "")
    away=str(event.get("O2") or event.get("AwayTeam") or "")
    start=str(event.get("S") or event.get("StartTime") or event.get("start_time") or "")
    rows=[]
    for group in _groups(value):
        market=_market(group)
        for e in _outcomes(group):
            if not _is_player_market(group,e):
                continue
            direction=_direction(e)
            if direction not in {"over","under"}:
                continue
            player=str(e.get("PN") or e.get("PlayerName") or "").strip()
            odds=_f(e.get("C") or e.get("odds"))
            if not player or not odds or not (1.01 < odds <= 50):
                continue
            line=_f(e.get("P") if isinstance(e.get("P"),(int,float,str)) else None)
            if line is None:
                m=re.search(r"(\d+(?:\.\d+)?)", str(e.get("PL") or e.get("N") or ""))
                line=float(m.group(1)) if m else (0.5 if any(x in market for x in ("touchdown","home_run","goals")) else None)
            if line is None or line < 0:
                continue
            rows.append({
                "source":"1xbet_linefeed","bookmaker":"1xbet","sport":sport,"league":sport,
                "source_event_id":eid,"event_id":eid,"commence_time":start,
                "home_team":home,"away_team":away,"player_name":player,
                "market":market,"market_key":market,"direction":direction,
                "line":float(line),"odds_decimal":round(float(odds),4),
                "selection":str(e.get("PL") or e.get("N") or direction.title()),
                "raw":{"group":str(group.get("GS") or group.get("Name") or ""),"type":e.get("T"),"host":host},
            })
    return rows

def fetch_1xbet_props(sport: str, max_events: int=MAX_EVENTS) -> List[Dict[str, Any]]:
    sport=str(sport or "").upper()
    sid=SPORT_IDS.get(sport)
    if not ENABLED or not sid:
        return []
    max_events=max(1,min(int(max_events or MAX_EVENTS),MAX_EVENTS))
    for host in HOSTS:
        events=_list_events(host,sid)
        if not events:
            continue
        candidates=[e for e in events if isinstance(e,dict) and _league_ok(sport,e)]
        rows=[]
        for ev in candidates[:max_events]:
            eid=ev.get("I") or ev.get("CI") or ev.get("id")
            if not eid: continue
            payload=_game(host,eid)
            rows.extend(parse_game(payload,sport,ev,host))
        if rows:
            return rows
    return []
