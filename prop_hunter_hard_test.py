#!/usr/bin/env python3
"""Offline HARD TEST for PROP HUNTER 13.10.1. No external writes."""
from __future__ import annotations
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import prop_hunter_runtime_guard as guard

def check(v,msg):
    if not v: raise AssertionError(msg)

def test_runtime_guard(): guard.main()

def test_keyless_betrivers_relabel():
    import prop_hunter_keyless_books as kb
    listing={"events":[{"event":{"id":99,"homeName":"Lakers","awayName":"Celtics","start":"2026-09-26T01:00:00Z"}}]}
    offer={"betOffers":[{"criterion":{"label":"Player Points"},"outcomes":[{"participant":"LeBron James","label":"Over 27.5","line":27500,"odds":1910},{"participant":"LeBron James","label":"Under 27.5","line":27500,"odds":1910}]}]}
    old=kb._get
    kb._get=lambda url,params=None: listing if "listView" in url else offer
    try: rows=kb.fetch_betrivers_props("NBA")
    finally: kb._get=old
    check(len(rows)==2,f"BetRivers expected 2 rows got {rows}")
    check(all(x["source"]=="betrivers_direct" and x["bookmaker"]=="betrivers" for x in rows),"BetRivers source relabel failed")

def test_snapshot_consensus_and_bad_row_filter():
    import prophunter as ph
    now=datetime.now(timezone.utc).isoformat()
    rows=[
        {"sport":"MLB","league":"MLB","source_event_id":"e1","player_name":"Player X","market":"hits","market_key":"hits","direction":"over","line":.5,"odds_decimal":1.91,"commence_time":now,"created_at":now,"home_team":"Home","away_team":"Away","bookmaker":"book_a","source":"fixture","raw":{}},
        {"sport":"MLB","league":"MLB","source_event_id":"e1","player_name":"Player X","market":"hits","market_key":"hits","direction":"under","line":.5,"odds_decimal":1.91,"commence_time":now,"created_at":now,"home_team":"Home","away_team":"Away","bookmaker":"book_a","source":"fixture","raw":{}},
        {"sport":"MLB","league":"MLB","source_event_id":"e1","player_name":"Player X","market":"hits","market_key":"hits","direction":"over","line":.5,"odds_decimal":2.05,"commence_time":now,"created_at":now,"home_team":"Home","away_team":"Away","bookmaker":"book_b","source":"fixture","raw":{}},
        {"sport":"MLB","league":"MLB","source_event_id":"e1","player_name":"Over 0.5","market":"hits","market_key":"hits","direction":"over","line":.5,"odds_decimal":9.99,"commence_time":now,"created_at":now,"home_team":"Home","away_team":"Away","bookmaker":"bad","source":"fixture","raw":{}},
    ]
    class R:
        def __init__(self,data): self.data=data
    class Q:
        def __init__(self,data): self.data=data
        def select(self,*a,**k): return self
        def gte(self,*a,**k): return self
        def limit(self,*a,**k): return self
        def lte(self,*a,**k): return self
        def order(self,*a,**k): return self
        def range(self,start,end):
            self.data=self.data[start:end+1]
            return self
        def execute(self): return R(self.data)
    class SB:
        def table(self,*a,**k): return Q(rows)
    old=ph._sb_read; ph._sb_read=lambda:SB()
    try: props=ph.fetch_snapshot_props("MLB")
    finally: ph._sb_read=old
    check(all(p.player!="Over 0.5" for p in props),"bad player row leaked")
    overs=[p for p in props if p.direction=="over"]
    check(len(overs)==1,"best-price dedupe failed")
    check(abs(float(overs[0].odds)-2.05)<.001,"best observed price not kept")
    check((overs[0].features or {}).get("fair_prob") is not None,"no-vig fair missing")

def test_orchestrator_keyless_first_and_quota_skip():
    import prop_hunter_source_orchestrator as orch
    source=Path("prop_hunter_source_orchestrator.py").read_text()
    dk=source.index("draftkings_direct_"); kambi=source.index("kambi_"); optic=source.index("opticodds_"); oddspapi=source.index("oddspapi_")
    check(dk<kambi<optic,"keyless-first source order regressed")
    check(oddspapi>optic,"OddsPapi missing/restored in wrong layer")
    rows=[]
    for b in range(5):
        for i in range(15):
            for side in ("over","under"):
                rows.append({"sport":"MLB","bookmaker":f"b{b}","player_name":f"P{i}","market_key":"hits","line":.5,"direction":side,"odds_decimal":1.9})
    n,books,pairs=orch._coverage(rows,"MLB")
    check((n,books,pairs)==(150,5,75),f"coverage wrong {(n,books,pairs)}")

def test_workflows_and_runtime():
    card=Path(".github/workflows/prophunter.yml").read_text(); maint=Path(".github/workflows/prop_hunter_maintenance.yml").read_text()
    for text in (card,maint):
        check("13.10.1-KEYLESS-HARDENED" in text,"workflow runtime stale")
        check("PH_KEYLESS_BOOKS_ENABLED: '1'" in text,"keyless books not enabled")
        check("PH_KEYLESS_MAX_EVENTS" in text and "PH_KEYLESS_MAX_PROP_CATEGORIES" in text,"keyless bounds missing")
        check("PH_BROWSER_ENABLED: '0'" in text,"browser gate regressed")
    check("OPTICODDS_API_KEY" in card,"OpticOdds trial fallback missing")
    check("PH_ODDSPAPI_MAX_EVENTS" in card,"OddsPapi bounded fallback missing")

def test_source_audit_catalog():
    audit=Path("prop_hunter_source_audit.py").read_text(); cat=Path("prop_hunter_source_catalog.py").read_text()
    for name in ("draftkings_direct","fanduel_direct","bovada_direct","betrivers_direct"):
        check(name in audit,f"{name} missing audit")
        check(name in cat,f"{name} missing catalog")
    check("prop_hunter_quote_guard.py" in audit and "prop_hunter_keyless_books.py" in audit,"new critical modules missing audit")

def test_no_network_in_hard_test():
    import ast
    tree=ast.parse(Path("prop_hunter_hard_test.py").read_text())
    bad=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):
            root=node.func.value
            if isinstance(root,ast.Name) and root.id in {"requests","urllib","httpx"}:
                bad.append(f"{root.id}.{node.func.attr}")
    check(not bad,f"hard test contains network call(s): {bad}")

def main():
    tests=[test_runtime_guard,test_keyless_betrivers_relabel,test_snapshot_consensus_and_bad_row_filter,test_orchestrator_keyless_first_and_quota_skip,test_workflows_and_runtime,test_source_audit_catalog,test_no_network_in_hard_test]
    for t in tests:
        t(); print(f"HARD TEST OK: {t.__name__}")
    print(f"HARD TEST PASSED: {len(tests)}/{len(tests)} suites")
if __name__=="__main__": main()
