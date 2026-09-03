#!/usr/bin/env python3
from __future__ import annotations
import os
import prophunter as ph
from prop_hunter_builder_engine import build_autonomous_extras
from prop_hunter_oddspapi import TARGETS as _OP_TARGETS, parse_odds_payload as _op_parse
from prop_hunter_http import get as _http_get

EXPECTED=os.getenv("PH_EXPECTED_RUNTIME_VERSION","13.6-ODDSPLUS")

def fail(msg): raise SystemExit(f"RUNTIME GUARD FAILED: {msg}")

def main():
    if getattr(ph,"PH_RUNTIME_VERSION",None)!=EXPECTED:
        fail(f"runtime={getattr(ph,'PH_RUNTIME_VERSION',None)} expected={EXPECTED}")
    synthetic=ph.Prop(player="Fake",market="Points",odds=1.85,point=20.5,sport="WNBA",emoji="🏀",game="A @ B",direction="over",features={"odds_observed":False,"price_type":"synthetic","bookmaker":"synthetic"})
    if ph._has_observed_price(synthetic): fail("synthetic price accepted")
    real=ph.Prop(player="Real",market="Points",odds=1.95,point=20.5,sport="WNBA",emoji="🏀",game="A @ B",direction="over",features={"odds_observed":True,"price_type":"bookmaker","bookmaker":"bet365","fair_prob":0.60})
    if not ph._has_observed_price(real): fail("observed price rejected")
    pick=ph.Pick(type="single",player="Real",market="Points Over 20.5",direction="over",odds=1.95,stake=.2,probability=.60,edge_pct=17,ev=.17,game="A @ B",emoji="🏀")
    pick.point=20.5; pick.sport="WNBA"; pick.features=real.features
    extras=build_autonomous_extras([pick],[real],ph.Pick,ph.LadderLeg)
    if any(x.type=="ladder" for x in extras): fail("ladder invented without observed alternate line")
    if not hasattr(ph, "fetch_nhl_player_gamelogs"):
        fail("NHL gamelog support missing")
    if not all(k in _OP_TARGETS for k in ("baseball_mlb","basketball_nba","basketball_wnba","americanfootball_nfl","icehockey_nhl")):
        fail("OddsPapi target registry incomplete")
    if not callable(_op_parse) or not callable(_http_get):
        fail("OddsPapi/curl_cffi helpers missing")
    print("NHL gamelog support: OK")
    print("OddsPapi dynamic discovery: OK")
    print("curl_cffi HTTP fallback: OK")
    print(f"RUNTIME GUARD OK: {EXPECTED}")
    print("Synthetic odds rejected: OK")
    print("Observed sportsbook odds accepted: OK")
    print("No invented ladder from one line: OK")

if __name__=="__main__": main()
