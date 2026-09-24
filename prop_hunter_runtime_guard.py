#!/usr/bin/env python3
from __future__ import annotations
import os
import prophunter as ph
from prop_hunter_1xbet import parse_game as xbet_parse
from prop_hunter_builder_engine import build_autonomous_extras
from prop_hunter_identity_hub import identity_match
from prop_hunter_kambi import parse_offer as kambi_parse
from prop_hunter_market_consensus import enrich as consensus_enrich, fair_prob_for
from prop_hunter_parlayapi import parse_rows as parlay_parse
from prop_hunter_propline import parse_payload as propline_parse
from prop_hunter_settler import find_gamelog,line_of_pick,stat_value
from prop_hunter_sgo import parse_events as sgo_parse
from prop_hunter_shared_utils import _json_clean
from prop_hunter_source_manager import source_weight
EXPECTED=os.getenv("PH_EXPECTED_RUNTIME_VERSION","13.10.0-MULTISOURCE-CONSENSUS")
def fail(msg):raise SystemExit(f"RUNTIME GUARD FAILED: {msg}")
def source_checks():
    sgo=sgo_parse([{"eventID":"sgo-1","startTime":"2026-09-25T23:00:00Z","teams":{"home":{"names":{"long":"Lakers"}},"away":{"names":{"long":"Celtics"}}},"odds":{"x":{"statID":"assists","betTypeID":"ou","statEntityID":"LEBRON_JAMES_1_NBA","sideID":"over","overUnder":7.5,"byBookmaker":{"draftkings":{"available":True,"overUnder":7.5,"odds":-110,"altLines":[{"available":True,"overUnder":8.5,"odds":120}]}}}}}],"NBA")
    if len(sgo)!=2 or {float(x["line"]) for x in sgo}!={7.5,8.5}:fail("SGO alt lines")
    k=kambi_parse({"betOffers":[{"criterion":{"label":"Player Points"},"outcomes":[{"participant":"LeBron James","label":"Over 27.5","line":27500,"odds":1910},{"participant":"LeBron James","label":"Under 27.5","line":27500,"odds":1910}]}]},"NBA","k1","Lakers","Celtics","2026-09-25T23:00:00Z","ub")
    if len(k)!=2 or any(float(x["line"])!=27.5 for x in k):fail(f"Kambi milli-line parse: {k}")
    xb=xbet_parse({"Value":{"GE":[{"GS":"Player Points","E":[[{"PN":"LeBron James","PL":"Over 27.5","P":27.5,"C":1.91,"T":9},{"PN":"LeBron James","PL":"Under 27.5","P":27.5,"C":1.91,"T":10}]]}]}},"NBA",{"I":123,"O1":"Lakers","O2":"Celtics"},"fixture")
    if len(xb)!=2 or {x["direction"] for x in xb}!={"over","under"}:fail(f"1xBet parse: {xb}")
    pp=parlay_parse({"data":[{"event_id":"p1","player":"LeBron James","market":"player_points","line":27.5,"bookmaker":"draftkings","over_price":-110,"under_price":-110,"home_team":"Lakers","away_team":"Celtics"}]},"NBA")
    if len(pp)!=2 or any((x.get("raw") or {}).get("paired_fair_prob") is None for x in pp):fail("ParlayAPI pair parse")
    pl=propline_parse([{"id":"pl1","home_team":"Lakers","away_team":"Celtics","bookmakers":[{"key":"fanduel","markets":[{"key":"player_points","outcomes":[{"name":"Over","description":"LeBron James","point":27.5,"price":-115},{"name":"Under","description":"LeBron James","point":27.5,"price":-105}]}]}]}],"NBA")
    if len(pl)!=2:fail(f"PropLine parse: {pl}")
    cons=consensus_enrich([{"source":"kambi","bookmaker":"kambi_ub","sport":"NBA","home_team":"Lakers","away_team":"Celtics","commence_time":"2026-09-25T23:00:00Z","player_name":"LeBron James","market_key":"player_points","direction":"over","line":27.5,"odds_decimal":1.91},{"source":"kambi","bookmaker":"kambi_ub","sport":"NBA","home_team":"Lakers","away_team":"Celtics","commence_time":"2026-09-25T23:00:00Z","player_name":"LeBron James","market_key":"points","direction":"under","line":27.5,"odds_decimal":1.91}])
    if not all(fair_prob_for(x) and abs(fair_prob_for(x)-.5)<.001 for x in cons):fail("no-vig consensus")
def safety_checks():
    synthetic=ph.Prop(player="Fake",market="Points",odds=1.85,point=20.5,sport="WNBA",emoji="🏀",game="A @ B",direction="over",features={"odds_observed":False,"price_type":"synthetic","bookmaker":"synthetic"})
    if ph._has_observed_price(synthetic):fail("synthetic odds accepted")
    real=ph.Prop(player="Real",market="Points",odds=1.95,point=20.5,sport="WNBA",emoji="🏀",game="A @ B",direction="over",features={"odds_observed":True,"price_type":"bookmaker","bookmaker":"book","fair_prob":.60})
    if not ph._has_observed_price(real):fail("observed odds rejected")
    pick=ph.Pick(type="single",player="Real",market="Points Over 20.5",direction="over",odds=1.95,stake=.2,probability=.60,edge_pct=17,ev=.17,game="A @ B",emoji="🏀");pick.point=20.5;pick.sport="WNBA";pick.features=real.features
    if any(x.type=="ladder" for x in build_autonomous_extras([pick],[real],ph.Pick,ph.LadderLeg)):fail("invented ladder")
    if line_of_pick({"market":"Points Over 20.5"})!=20.5:fail("line fallback")
    if stat_value({"league":"NFL","passing_tds":3},"passing_touchdowns")!=3:fail("NFL alias")
    logs=[{"player_name":"Shohei Ohtani","game_date":"2026-09-18","game_id":"a"},{"player_name":"Shohei Ohtani","game_date":"2026-09-18","game_id":"b"}]
    if find_gamelog({"player":"Shohei Ohtani","commence_time":"2026-09-19T01:00:00Z","market":"Hits Over .5"},logs) is not None:fail("doubleheader ambiguity")
    if not identity_match("Patrick Mahomes II","Patrick Mahomes",threshold=94):fail("identity")
    if not (.70<=source_weight("new-source")<=1.20):fail("source neutral weight")
    if _json_clean({"x":float("nan")})!={"x":None}:fail("json sanitizer")
def main():
    if getattr(ph,"PH_RUNTIME_VERSION",None)!=EXPECTED:fail(f"runtime={getattr(ph,'PH_RUNTIME_VERSION',None)} expected={EXPECTED}")
    source_checks();safety_checks();print("RUNTIME GUARD: SGO/Kambi/1xBet/PropLine/ParlayAPI parsers OK");print("RUNTIME GUARD: no-vig consensus + observed-price safety OK");print("RUNTIME GUARD: settlement/identity/source-weight safety OK");print(f"RUNTIME GUARD OK: {EXPECTED}")
if __name__=="__main__":main()
