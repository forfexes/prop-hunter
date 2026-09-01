#!/usr/bin/env python3
from __future__ import annotations
import os
import prophunter as ph
from prop_hunter_builder_engine import build_autonomous_extras

EXPECTED=os.getenv("PH_EXPECTED_RUNTIME_VERSION","13.4-PRESEASON-READY")

def fail(msg): raise SystemExit(f"RUNTIME GUARD FAILED: {msg}")

def main():
    if getattr(ph,"PH_RUNTIME_VERSION",None)!=EXPECTED: fail(f"runtime={getattr(ph,'PH_RUNTIME_VERSION',None)} expected={EXPECTED}")
    synthetic=ph.Prop(player="Fake",market="Points",odds=1.85,point=20.5,sport="WNBA",emoji="🏀",game="A @ B",direction="over",features={"odds_observed":False,"price_type":"synthetic","bookmaker":"synthetic"})
    if ph._has_observed_price(synthetic): fail("synthetic price accepted")
    real=ph.Prop(player="Real",market="Points",odds=1.95,point=20.5,sport="WNBA",emoji="🏀",game="A @ B",direction="over",features={"odds_observed":True,"price_type":"bookmaker","bookmaker":"bet365","fair_prob":0.60})
    if not ph._has_observed_price(real): fail("observed price rejected")
    # Builder must not invent an alternate ladder from a single line.
    pick=ph.Pick(type="single",player="Real",market="Points Over 20.5",direction="over",odds=1.95,stake=.2,probability=.60,edge_pct=17,ev=.17,game="A @ B",emoji="🏀")
    pick.point=20.5; pick.sport="WNBA"; pick.features=real.features
    extras=build_autonomous_extras([pick],[real],ph.Pick,ph.LadderLeg)
    if any(x.type=="ladder" for x in extras): fail("ladder invented without observed alternate line")
    print(f"RUNTIME GUARD OK: {EXPECTED}")
    print("Synthetic odds rejected: OK")
    print("Observed sportsbook odds accepted: OK")
    print("No invented ladder from one line: OK")

if __name__=="__main__": main()
