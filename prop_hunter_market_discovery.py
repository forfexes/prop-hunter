#!/usr/bin/env python3
"""PROP HUNTER — automatic market discovery in shadow mode."""
from __future__ import annotations
from collections import Counter, defaultdict
import re
from prop_hunter_shared_utils import select_rows, safe_json_write, now_iso, norm_market, log

KNOWN=("point","rebound","assist","pra","three","3pm","steal","block","turnover","hit","total base","home run","rbi","run","stolen base","strikeout","receiving","rushing","passing","reception","touchdown","anytime td","shot on goal","goalie save","power play")

def base(m):
    s=norm_market(m); s=re.sub(r"\b(over|under|plus)\b|\d+(?:\s+\d+)?"," ",s)
    return re.sub(r"\s+"," ",s).strip()

def main():
    rows=select_rows("prop_hunter_prop_snapshots", limit=15000)
    counts=Counter(); sports=defaultdict(Counter); samples={}
    for r in rows:
        m=base(r.get("market_key") or r.get("market"))
        if not m: continue
        counts[m]+=1; sports[m][str(r.get("sport") or r.get("league") or "UNKNOWN").upper()]+=1
        samples.setdefault(m, r.get("market_key") or r.get("market"))
    discovered=[]
    for m,n in counts.most_common():
        known=any(k in m for k in KNOWN)
        discovered.append({"market_base":m,"sample":samples[m],"observations":n,"sports":dict(sports[m]),
                           "status":"known" if known else "shadow","auto_enable":False if not known else True})
    report={"updated_at":now_iso(),"markets":discovered,"shadow_count":sum(1 for x in discovered if x["status"]=="shadow")}
    safe_json_write("prop_hunter_market_discovery.json",report)
    log(f"market discovery: markets={len(discovered)} shadow={report['shadow_count']}")

if __name__ == "__main__": main()
