#!/usr/bin/env python3
"""Probe public SIHF National League per-game player-stat export links."""
from __future__ import annotations
import re
from urllib.parse import urljoin
import requests

GAME_ID="20271105000054"
URL=f"https://www.sihf.ch/de/game-center/game/spielerstatistik/{GAME_ID}"
HEADERS={"User-Agent":"PROP-HUNTER/swiss-nl-probe","Accept":"text/html,*/*"}

def main():
    r=requests.get(URL,headers=HEADERS,timeout=20)
    print("SIHF_PAGE",r.status_code,len(r.text),r.url,flush=True)
    r.raise_for_status()
    hrefs=re.findall(r'href=["\']([^"\']+)["\']',r.text,re.I)
    candidates=[urljoin(URL,h) for h in hrefs if re.search(r'csv|export|download|player|goalie|stat',h,re.I)]
    print("SIHF_CANDIDATES",len(candidates),flush=True)
    for x in candidates[:100]:
        print("SIHF_LINK",x,flush=True)
    for m in re.finditer(r'.{0,180}CSV.{0,220}',r.text,re.I|re.S):
        print("SIHF_CSV_CONTEXT",re.sub(r'\s+',' ',m.group(0))[:450],flush=True)

    base="https://www.sihf.ch/umbraco/GameCenter/GameDetail/ExportGamePlayerStats"
    for alias in ("gamePlayerStatsHome","gamePlayerStatsAway","gameGoalieStatsHome","gameGoalieStatsAway"):
        x=requests.get(base,params={"gameId":GAME_ID,"format":"Csv","alias":alias},headers=HEADERS,timeout=20)
        print("SIHF_EXPORT",alias,x.status_code,x.headers.get("content-type"),len(x.content),flush=True)
        text=x.content.decode("utf-8-sig",errors="replace")
        print("SIHF_EXPORT_BEGIN",alias,flush=True)
        print("\n".join(text.splitlines()[:12]),flush=True)
        print("SIHF_EXPORT_END",alias,flush=True)

    schedule="https://www.sihf.ch/de/game-center/liga/spielplan/1-1"
    sr=requests.get(schedule,headers=HEADERS,timeout=20)
    print("SIHF_SCHEDULE",sr.status_code,len(sr.text),sr.url,flush=True)
    sr.raise_for_status()
    shrefs=re.findall(r'href=["\']([^"\']+)["\']',sr.text,re.I)
    game_links=[urljoin(schedule,h) for h in shrefs if re.search(r'/game(?:/|$)|spielerstatistik',h,re.I)]
    print("SIHF_SCHEDULE_GAME_LINKS",len(game_links),flush=True)
    for x in game_links[:80]:
        print("SIHF_GAME_LINK",x,flush=True)
    for m in re.finditer(r'.{0,200}(?:season|saison).{0,300}',sr.text,re.I|re.S):
        print("SIHF_SEASON_CONTEXT",re.sub(r'\s+',' ',m.group(0))[:520],flush=True)

if __name__=="__main__":
    main()
