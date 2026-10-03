#!/usr/bin/env python3
"""Probe public SHL Statnet reports before enabling persistence."""
from __future__ import annotations
import re
import requests

URL = "https://reports.statnet.se/shl/"
HEADERS = {"User-Agent": "PROP-HUNTER/shl-probe", "Accept": "text/html,*/*"}


def main():
    r=requests.get(URL,timeout=15,headers=HEADERS)
    print("SHL_STATNET_INDEX",r.status_code,len(r.text),r.url,flush=True)
    r.raise_for_status()
    hrefs=re.findall(r'href=["\']([^"\']+)["\']',r.text,re.I)
    texts=re.findall(r'>([^<>]{1,120}PlayerReport[^<>]{0,120})<',r.text,re.I)
    player_links=[h for h in hrefs if "player" in h.lower() and ("report" in h.lower() or "stats" in h.lower())]
    print("SHL_STATNET_HREFS",len(hrefs),flush=True)
    print("SHL_STATNET_PLAYER_LINKS",player_links[:20],flush=True)
    print("SHL_STATNET_TEXTS",texts[:20],flush=True)
    print("SHL_STATNET_HREF_SAMPLE",hrefs[:80],flush=True)


if __name__=="__main__":
    main()
