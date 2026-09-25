#!/usr/bin/env python3
"""Offline hard test for PROP HUNTER 13.10. No network/API writes."""
from __future__ import annotations
from datetime import datetime,timezone
from pathlib import Path
import prop_hunter_runtime_guard as guard
def check(v,msg):
    if not v:raise AssertionError(msg)
def test_guard():guard.main()
def test_snapshot_consensus():
    import prophunter as ph
    now=datetime.now(timezone.utc).isoformat();rows=[{"sport":"MLB","league":"MLB","source_event_id":"e1","player_name":"Player X","market":"batter_hits","market_key":"batter_hits","direction":"over","line":.5,"odds_decimal":1.91,"commence_time":now,"created_at":now,"home_team":"Home","away_team":"Away","bookmaker":"book_a","source":"fixture","raw":{}},{"sport":"MLB","league":"MLB","source_event_id":"e1","player_name":"Player X","market":"hits","market_key":"hits","direction":"under","line":.5,"odds_decimal":1.91,"commence_time":now,"created_at":now,"home_team":"Home","away_team":"Away","bookmaker":"book_a","source":"fixture","raw":{}},{"sport":"MLB","league":"MLB","source_event_id":"e1","player_name":"Player X","market":"hits","market_key":"hits","direction":"over","line":.5,"odds_decimal":2.05,"commence_time":now,"created_at":now,"home_team":"Home","away_team":"Away","bookmaker":"book_b","source":"fixture","raw":{}}]
    class R:
        def __init__(self,data):self.data=data
    class Q:
        def __init__(self,data):self.data=data
        def select(self,*a,**k):return self
        def gte(self,*a,**k):return self
        def limit(self,*a,**k):return self
        def execute(self):return R(self.data)
    class SB:
        def table(self,*a,**k):return Q(rows)
    old=ph._sb_read;ph._sb_read=lambda:SB()
    try:props=ph.fetch_snapshot_props("MLB")
    finally:ph._sb_read=old
    overs=[p for p in props if p.direction=="over"];check(len(overs)==1,"best-price dedupe failed");check(abs(float(overs[0].odds)-2.05)<.001,"best observed price not kept");check((overs[0].features or {}).get("fair_prob") is not None,"no-vig fair probability missing")
def test_orchestrator_coverage():
    import prop_hunter_source_orchestrator as orch
    rows=[]
    for b in range(5):
        for i in range(12):
            for side in ("over","under"):rows.append({"sport":"MLB","bookmaker":f"b{b}","player_name":f"P{i}","market_key":"hits","line":.5,"direction":side,"odds_decimal":1.9})
    n,books,pairs=orch._coverage(rows,"MLB");check((n,books,pairs)==(120,5,60),f"coverage wrong {(n,books,pairs)}")
def test_workflow():
    card=Path(".github/workflows/prophunter.yml").read_text();maint=Path(".github/workflows/prop_hunter_maintenance.yml").read_text()
    for text in (card,maint):check("13.10.0-MULTISOURCE-CONSENSUS" in text,"workflow runtime stale")
    check("OPTICODDS_API_KEY" in card and "PH_OPTICODDS_MAX_FIXTURES: '5'" in card,"OpticOdds trial source missing")
    check("PARLAY_API_KEY" in card and "PROPLINE_API_KEY" in card,"new keyed sources missing");check("PH_1XBET_ENABLED: '1'" in card,"1xBet not enabled");check("PH_KAMBI_MAX_BRANDS: '4'" in card,"Kambi multi-brand not enabled");check("PH_BROWSER_ENABLED: '0'" in card,"browser gate regressed")
    check(Path("prop_hunter_opticodds.py").exists(),"OpticOdds adapter missing")
def main():
    tests=[test_guard,test_snapshot_consensus,test_orchestrator_coverage,test_workflow]
    for t in tests:t();print(f"HARD TEST OK: {t.__name__}")
    print(f"HARD TEST PASSED: {len(tests)}/{len(tests)} suites")
if __name__=="__main__":main()
