#!/usr/bin/env python3
"""PROP HUNTER — coverage watchdog.

Detects silent loss of sports/markets/sources from recent stored snapshots.
No external calls; safe for a short card/result run.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from prop_hunter_shared_utils import select_rows, safe_json_write, now_iso, log

CORE={
 "MLB":("home run","hits","total bases","rbi","pitcher strikeouts"),
 "NBA":("points","rebounds","assists","threes"),
 "WNBA":("points","rebounds","assists","threes"),
 "NFL":("touchdown","receiving","rushing","passing","receptions"),
 "NHL":("shots","goals","points","assists","saves"),
}

def _dt(v):
    try:
        d=datetime.fromisoformat(str(v).replace("Z","+00:00"));
        if d.tzinfo is None: d=d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc)
    except Exception: return None

def main():
    rows=select_rows("prop_hunter_prop_snapshots", limit=15000)
    cutoff=datetime.now(timezone.utc)-timedelta(hours=36)
    bysport=defaultdict(lambda:{"rows":0,"sources":set(),"markets":set(),"latest":None})
    for r in rows:
        d=_dt(r.get("created_at") or r.get("created_at_utc"))
        if d and d<cutoff: continue
        sport=str(r.get("sport") or r.get("league") or "UNKNOWN").upper()
        x=bysport[sport]; x["rows"]+=1
        s=str(r.get("source") or r.get("bookmaker") or "").lower().strip()
        if s: x["sources"].add(s)
        m=str(r.get("market_key") or r.get("market") or "").lower()
        if m: x["markets"].add(m)
        if d and (x["latest"] is None or d>x["latest"]): x["latest"]=d
    issues=[]; summary={}
    for sport,expected in CORE.items():
        x=bysport.get(sport,{"rows":0,"sources":set(),"markets":set(),"latest":None})
        missing=[]
        for needle in expected:
            if not any(needle in m for m in x["markets"]): missing.append(needle)
        if x["rows"]==0: issues.append({"sport":sport,"severity":"high","issue":"no_recent_rows"})
        elif len(x["sources"])<2: issues.append({"sport":sport,"severity":"medium","issue":"single_source","sources":sorted(x["sources"])})
        if missing: issues.append({"sport":sport,"severity":"low","issue":"market_gaps","markets":missing})
        summary[sport]={"rows":x["rows"],"sources":sorted(x["sources"]),"market_count":len(x["markets"]),
                        "latest":x["latest"].isoformat() if x["latest"] else None,"missing_core":missing}
    safe_json_write("prop_hunter_coverage_report.json",{"updated_at":now_iso(),"window_hours":36,"sports":summary,"issues":issues})
    log(f"coverage watchdog: recent_rows={sum(x['rows'] for x in bysport.values())} issues={len(issues)}")

if __name__ == "__main__": main()
