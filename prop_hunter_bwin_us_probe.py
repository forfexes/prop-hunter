#!/usr/bin/env python3
"""Audit US-sport quote coverage without fabricating player prices.

NETRATTLER's Bwin collector targets soccer sportIds=4 and team markets.
This probe checks public Bwin US fixture catalogs, but never publishes odds.
"""
import json
import os
import requests

BASE="https://sports.bwin.com/cds-api/bettingoffer/fixtures"
# Bwin catalog sport IDs are configurable: do not assume they are stable.
SPORT_IDS={k:os.getenv("PH_BWIN_"+k+"_SPORT_ID","") for k in ("NBA","NHL","NFL","MLB")}
PARAMS={"x-bwin-accessid":os.getenv("PH_BWIN_ACCESS_ID",""),"lang":"en","country":"GB","userCountry":"GB","state":"Latest","offerMapping":"Filtered","fixtureTypes":"Standard","skip":"0","take":"10"}
def probe(session=None):
    session=session or requests.Session()
    result={}
    for sport,sport_id in SPORT_IDS.items():
        if not sport_id:
            result[sport]={"status":"unconfigured","player_prop_quotes":0}
            continue
        try:
            response=session.get(BASE,params={**PARAMS,"sportIds":sport_id},timeout=6)
            response.raise_for_status()
            data=response.json()
            fixtures=data.get("fixtures",[]) if isinstance(data,dict) else []
            result[sport]={"status":"catalog_only","fixtures":len(fixtures),"player_prop_quotes":0}
        except (requests.RequestException,ValueError) as exc:
            result[sport]={"status":"unavailable","error":type(exc).__name__,"player_prop_quotes":0}
    return result
if __name__=="__main__":
    print(json.dumps(probe(),sort_keys=True))
