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

if __name__=="__main__":
    main()
