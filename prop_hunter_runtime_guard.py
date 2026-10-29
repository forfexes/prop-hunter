#!/usr/bin/env python3
"""Fast offline integrity guard for PROP HUNTER 13.10.1.

No network calls, Supabase writes or Telegram messages.  Fixtures exercise every
parser family plus the NETRATTLER-derived quote/model safety rules.
"""
from __future__ import annotations
import os
from pathlib import Path
import prophunter as ph
from prop_hunter_1xbet import parse_game as xbet_parse
from prop_hunter_builder_engine import build_autonomous_extras, _candidate_probability, _plausible_ladder_line, _sport
from prop_hunter_identity_hub import identity_match
from prop_hunter_kambi import parse_offer as kambi_parse
from prop_hunter_keyless_books import parse_draftkings_payload, parse_fanduel_event_page, parse_bovada_events
from prop_hunter_market_consensus import enrich as consensus_enrich, fair_prob_for
from prop_hunter_opticodds import parse_odds_payload as optic_parse
from prop_hunter_oddspapi import _keys as oddspapi_keys
from prop_hunter_parlayapi import parse_rows as parlay_parse
from prop_hunter_propline import parse_payload as propline_parse
from prop_hunter_quote_guard import sanitize_row, probability_sane
from prop_hunter_settler import find_gamelog, line_of_pick, stat_value
from prop_hunter_sgo import parse_events as sgo_parse
from prop_hunter_shared_utils import _json_clean
from prop_hunter_source_manager import source_weight

EXPECTED=os.getenv("PH_EXPECTED_RUNTIME_VERSION","13.10.1-KEYLESS-HARDENED")
def fail(msg): raise SystemExit(f"RUNTIME GUARD FAILED: {msg}")

def source_checks():
    _saved_keys={k:os.environ.get(k) for k in ("ODDSPAPI_KEYS","ODDSPAPI_KEY","ODDSPAPI","ODDSPAPI_API_KEY")}
    try:
        os.environ["ODDSPAPI_KEYS"]="key-a; key-b"
        os.environ["ODDSPAPI_KEY"]="key-b,key-c"
        os.environ.pop("ODDSPAPI",None);os.environ.pop("ODDSPAPI_API_KEY",None)
        if oddspapi_keys()!=["key-a","key-b","key-c"]: fail(f"OddsPapi key rotation parse: {oddspapi_keys()}")
    finally:
        for k,v in _saved_keys.items():
            if v is None: os.environ.pop(k,None)
            else: os.environ[k]=v
    sgo=sgo_parse([{"eventID":"sgo-1","startTime":"2026-09-25T23:00:00Z","teams":{"home":{"names":{"long":"Lakers"}},"away":{"names":{"long":"Celtics"}}},"odds":{"x":{"statID":"assists","betTypeID":"ou","statEntityID":"LEBRON_JAMES_1_NBA","sideID":"over","overUnder":7.5,"byBookmaker":{"draftkings":{"available":True,"overUnder":7.5,"odds":-110,"altLines":[{"available":True,"overUnder":8.5,"odds":120}]}}}}}],"NBA")
    if len(sgo)!=2 or {float(x["line"]) for x in sgo}!={7.5,8.5}: fail("SGO alt lines")

    dk=parse_draftkings_payload({
        "events":[{"id":"e1","name":"NY Mets @ ATL Braves","startEventDate":"2026-09-26T00:00:00Z"}],
        "markets":[{"id":"m1","eventId":"e1","name":"Mookie Betts Hits O/U"},{"id":"m2","eventId":"e1","name":"Aaron Judge Home Runs"}],
        "selections":[
            {"marketId":"m1","label":"Over 1.5","points":1.5,"displayOdds":{"american":"+120"}},
            {"marketId":"m1","label":"Under 1.5","points":1.5,"displayOdds":{"american":"-150"}},
            {"marketId":"m2","label":"1+","displayOdds":{"american":"+250"}},
            {"marketId":"m2","label":"2+","displayOdds":{"american":"+900"}},
        ],
    },"MLB")
    if len(dk)!=4 or {x["direction"] for x in dk[:2]}!={"over","under"}: fail(f"DraftKings direct parse: {dk}")
    judge=[x for x in dk if x["player_name"]=="Aaron Judge"]
    if {x["line"] for x in judge}!={0.5,1.5}: fail(f"DraftKings X+ ladders: {judge}")

    fd=parse_fanduel_event_page({"attachments":{"markets":{"m1":{"marketName":"To Record 2+ Hits","runners":[{"runnerName":"Mookie Betts","isPlayerSelection":True,"winRunnerOdds":{"americanDisplayOdds":{"americanOdds":-110}}}]},"m2":{"marketName":"To Hit A Home Run","runners":[{"runnerName":"Shohei Ohtani","isPlayerSelection":True,"winRunnerOdds":{"americanDisplayOdds":{"americanOdds":1000}}}]}}}},"MLB",{"eventId":"fd1","name":"NY Mets @ ATL Braves","openDate":"2026-09-26T00:00:00Z"})
    if len(fd)!=2 or sorted(x["line"] for x in fd)!=[0.5,1.5]: fail(f"FanDuel direct parse: {fd}")
    fd_ou=parse_fanduel_event_page({"attachments":{"markets":{"m3":{"marketName":"Player Points","runners":[{"runnerName":"LeBron James Over 27.5","isPlayerSelection":True,"handicap":27.5,"winRunnerOdds":{"americanDisplayOdds":{"americanOdds":-110}}},{"runnerName":"LeBron James Under 27.5","isPlayerSelection":True,"handicap":27.5,"winRunnerOdds":{"americanDisplayOdds":{"americanOdds":-110}}}]}}}},"NBA",{"eventId":"fd2","name":"Celtics @ Lakers","openDate":"2026-09-26T01:00:00Z"})
    if len(fd_ou)!=2 or {x["direction"] for x in fd_ou}!={"over","under"} or any(x["player_name"]!="LeBron James" for x in fd_ou): fail(f"FanDuel O/U player normalization: {fd_ou}")
    fd_wrong_event=parse_fanduel_event_page({"attachments":{"markets":{"m4":{"eventId":"fd-other","marketName":"Player Hits","runners":[{"runnerName":"Jo Adell Over 0.5","isPlayerSelection":True,"handicap":0.5,"winRunnerOdds":{"americanDisplayOdds":{"americanOdds":-110}}}]}}}},"MLB",{"eventId":"fd-target","name":"White Sox @ Guardians","openDate":"2026-10-03T17:00:00Z"})
    if fd_wrong_event: fail(f"FanDuel cross-event attachment accepted: {fd_wrong_event}")

    bov=parse_bovada_events([{"id":"b1","startTime":1790380800000,"competitors":[{"name":"Away","home":False},{"name":"Home","home":True}],"displayGroups":[{"description":"Player Props","markets":[{"description":"Total Hits - Mookie Betts (LAD)","status":"O","outcomes":[{"description":"Over","status":"O","price":{"american":"-110","handicap":"1.5"}},{"description":"Under","status":"O","price":{"american":"-110","handicap":"1.5"}}]}]}]}],"MLB")
    if len(bov)!=2 or {x["direction"] for x in bov}!={"over","under"}: fail(f"Bovada direct parse: {bov}")
    bov_combo=parse_bovada_events([{"id":"b2","startTime":1790380800000,"competitors":[{"name":"Away","home":False},{"name":"Home","home":True}],"displayGroups":[{"description":"Player Props","markets":[{"description":"Total Passing & Rushing Yards O/U - Cam Ward (TEN)","status":"O","outcomes":[{"description":"Over","status":"O","price":{"american":"-110","handicap":"198.5"}},{"description":"Under","status":"O","price":{"american":"-110","handicap":"198.5"}}]}]}]}],"NFL")
    if bov_combo: fail(f"Bovada combined passing+rushing market reached card pipeline: {bov_combo}")

    k=kambi_parse({"betOffers":[{"criterion":{"label":"Player Points"},"outcomes":[{"participant":"LeBron James","label":"Over 27.5","line":27500,"odds":1910},{"participant":"LeBron James","label":"Under 27.5","line":27500,"odds":1910}]}]},"NBA","k1","Lakers","Celtics","2026-09-25T23:00:00Z","ub")
    if len(k)!=2 or any(float(x["line"])!=27.5 for x in k): fail(f"Kambi milli-line parse: {k}")
    xb=xbet_parse({"Value":{"GE":[{"GS":"Player Points","E":[[{"PN":"LeBron James","PL":"Over 27.5","P":27.5,"C":1.91,"T":9},{"PN":"LeBron James","PL":"Under 27.5","P":27.5,"C":1.91,"T":10}]]}]}},"NBA",{"I":123,"O1":"Lakers","O2":"Celtics"},"fixture")
    if len(xb)!=2 or {x["direction"] for x in xb}!={"over","under"}: fail(f"1xBet parse: {xb}")
    oo=optic_parse({"data":[{"id":"oo1","start_date":"2026-09-25T23:00:00Z","home_team_display":"Lakers","away_team_display":"Celtics","odds":[{"sportsbook":"DraftKings","market":"Player Points","market_id":"player_points","name":"LeBron James Over 27.5","selection":"LeBron James","selection_line":"over","points":27.5,"player_id":"P1","price":1.91},{"sportsbook":"DraftKings","market":"Player Points","market_id":"player_points","name":"LeBron James Under 27.5","selection":"LeBron James","selection_line":"under","points":27.5,"player_id":"P1","price":1.91}]}]},"NBA")
    if len(oo)!=2: fail(f"OpticOdds parse: {oo}")
    pp=parlay_parse({"data":[{"event_id":"p1","player":"LeBron James","market":"player_points","line":27.5,"bookmaker":"draftkings","over_price":-110,"under_price":-110}]},"NBA")
    if len(pp)!=2: fail("ParlayAPI pair parse")
    pl=propline_parse([{"id":"pl1","bookmakers":[{"key":"fanduel","markets":[{"key":"player_points","outcomes":[{"name":"Over","description":"LeBron James","point":27.5,"price":-115},{"name":"Under","description":"LeBron James","point":27.5,"price":-105}]}]}]}],"NBA")
    if len(pl)!=2: fail(f"PropLine parse: {pl}")

    cons=consensus_enrich([
        {"source":"bovada_direct","bookmaker":"bovada","sport":"MLB","home_team":"Home","away_team":"Away","commence_time":"2026-09-25T23:00:00Z","player_name":"Mookie Betts","market_key":"hits","direction":"over","line":1.5,"odds_decimal":1.91},
        {"source":"bovada_direct","bookmaker":"bovada","sport":"MLB","home_team":"Home","away_team":"Away","commence_time":"2026-09-25T23:00:00Z","player_name":"Mookie Betts","market_key":"hits","direction":"under","line":1.5,"odds_decimal":1.91},
    ])
    if not all(fair_prob_for(x) and abs(fair_prob_for(x)-.5)<.001 for x in cons): fail("no-vig consensus")

def safety_checks():
    if sanitize_row({"player_name":"Over 0.5","market":"hits","direction":"over","line":.5,"odds_decimal":1.9}): fail("generic player label accepted")
    if sanitize_row({"player_name":"Lakers","home_team":"Lakers","away_team":"Celtics","market":"points","direction":"over","line":100.5,"odds_decimal":1.9}): fail("team label accepted as player")
    if sanitize_row({"player_name":"BYU","home_team":"TCU","away_team":"BYU (#10)","market":"points","direction":"under","line":27.5,"odds_decimal":1.77}): fail("ranked team label accepted as player")
    if sanitize_row({"player_name":"Total Points","home_team":"A","away_team":"B","market":"points","direction":"over","line":47.5,"odds_decimal":1.9}): fail("aggregate total accepted as player")
    if sanitize_row({"player_name":"Victor Wembanyama","sport":"NBA","market":"points","direction":"over","line":2.5,"odds_decimal":2.85}): fail("mislabeled NBA Points 2.5 accepted")
    if not sanitize_row({"player_name":"Victor Wembanyama","sport":"NBA","market":"threes","direction":"over","line":2.5,"odds_decimal":2.85}): fail("valid NBA Threes 2.5 rejected")
    if sanitize_row({"player_name":"BYU","home_team":"TCU","away_team":"BYU (#10)","market":"points","direction":"under","line":27.5,"odds_decimal":1.77}): fail("ranked team label accepted as player")
    combo=sanitize_row({"player_name":"Cam Ward","market":"rushing_yards","market_original":"Total Passing & Rushing Yards O/U - Cam Ward (TEN)","direction":"under","line":198.5,"odds_decimal":1.87})
    if combo: fail(f"combined passing+rushing market accepted as pure rushing: {combo}")
    binary=sanitize_row({"player_name":"Josh Allen","market":"anytime_td","direction":"yes","line":None,"odds_decimal":2.2,"selection":"Yes"})
    binary_line_one=sanitize_row({"player_name":"Josh Allen","market":"anytime_td","market_original":"Anytime TD","direction":"over","line":1,"odds_decimal":2.2})
    if not binary_line_one or binary_line_one["line"]!=.5: fail(f"binary placeholder line=1 not normalized: {binary_line_one}")
    if not binary or binary["line"]!=.5 or binary["direction"]!="over": fail("binary market normalization")
    if sanitize_row({"player_name":"Zay Flowers","market":"longest_reception","direction":"under","line":26.5,"odds_decimal":1.91}): fail("unsupported longest reception accepted")
    if sanitize_row({"player_name":"Zay Flowers","market":"player_to_score_a_touchdown_first_half","direction":"over","line":.5,"odds_decimal":4.0,"selection":"Yes"}): fail("period TD accepted as full-game TD")
    if sanitize_row({"player_name":"Cairo Santos","market":"goals","market_original":"Total Successful Field Goals by the Player - First Half","direction":"over","line":.5,"odds_decimal":1.7}): fail("period field-goal prop accepted as full-game")
    tackles=sanitize_row({"player_name":"Roquan Smith","market":"assists","market_original":"Total Defensive Tackles (both solo & assists) by the Player - Including Overtime","direction":"over","line":7.5,"odds_decimal":2.0})
    if not tackles or tackles["market_key"]!="tackles": fail(f"defensive tackles misclassified: {tackles}")
    fgm=sanitize_row({"player_name":"Cairo Santos","market":"goals","market_original":"Total Successful Field Goals by the Player - Including Overtime","direction":"over","line":1.5,"odds_decimal":1.9})
    if not fgm or fgm["market_key"]!="field_goals_made": fail(f"field goals misclassified: {fgm}")
    threes=sanitize_row({"player_name":"Allisha Gray","market":"goals","market_original":"2+ Three-Point Field Goals Made By The Player - Including Overtime","direction":"over","line":1.5,"odds_decimal":1.96})
    if not threes or threes["market_key"]!="threes": fail(f"three-point field goals misclassified: {threes}")
    td2=sanitize_row({"player_name":"Derrick Henry","market":"2_touchdown_to_be_scored_by_the_player_including_overtime","direction":"over","line":1.5,"odds_decimal":3.25,"selection":"Yes"})
    if not td2 or td2["market_key"]!="2_plus_td" or td2["line"]!=1.5: fail(f"2+ TD normalization failed: {td2}")
    td3=sanitize_row({"player_name":"Derrick Henry","market":"to_score_3_touchdowns","direction":"over","line":2.5,"odds_decimal":9.5,"selection":"Yes"})
    if not td3 or td3["market_key"]!="3_plus_td" or td3["line"]!=2.5: fail(f"3+ TD normalization failed: {td3}")
    if not probability_sane(.60,1.90): fail("reasonable model/market gap rejected")
    if probability_sane(.90,5.0): fail("absurd model/market gap accepted")

    synthetic=ph.Prop(player="Fake",market="Points",odds=1.85,point=20.5,sport="WNBA",emoji="🏀",game="A @ B",direction="over",features={"odds_observed":False,"price_type":"synthetic","bookmaker":"synthetic"})
    if ph._has_observed_price(synthetic): fail("synthetic odds accepted")
    real=ph.Prop(player="Real",market="Points",odds=1.95,point=20.5,sport="WNBA",emoji="🏀",game="A @ B",direction="over",features={"odds_observed":True,"price_type":"bookmaker","bookmaker":"book","fair_prob":.60})
    if not ph._has_observed_price(real): fail("observed odds rejected")
    if _candidate_probability(real) is None: fail("reasonable observed candidate rejected")
    absurd=ph.Prop(player="Wrong Match",market="Points",odds=5.0,point=20.5,sport="NBA",emoji="🏀",game="A @ B",direction="over",features={"odds_observed":True,"price_type":"bookmaker","bookmaker":"book","fair_prob":.90})
    if _candidate_probability(absurd) is not None: fail("builder model-market gap guard failed")
    basket_no_model=ph.Prop(player="No Model",market="Points",odds=1.83,point=20.5,sport="WNBA",emoji="🏀",game="A @ B",direction="over",enrichment="DATA+: Basket Line vorhanden",features={"odds_observed":True,"price_type":"bookmaker","bookmaker":"book"})
    if ph._source_prop_probability(basket_no_model) is not None: fail("basket rescue invented probability from line/odds")
    sport_pick=ph.Pick(type="single",player="Sport Check",market="Hits Over 0.5",direction="over",odds=1.9,stake=.1,probability=.6,edge_pct=7,ev=.14,game="A @ B",emoji="⚾")
    sport_pick.source_sport="MLB"
    if _sport(sport_pick)!="MLB": fail("builder lost source_sport identity")

    pick=ph.Pick(type="single",player="Real",market="Points Over 20.5",direction="over",odds=1.95,stake=.2,probability=.60,edge_pct=17,ev=.17,game="A @ B",emoji="🏀");pick.point=20.5;pick.sport="WNBA";pick.features=real.features
    if any(x.type=="ladder" for x in build_autonomous_extras([pick],[real],ph.Pick,ph.LadderLeg)): fail("invented ladder")
    ladder_easy=ph.Prop(player="Ladder Check",market="Hits",odds=4.0,point=.5,sport="MLB",emoji="⚾",game="A @ B",direction="over",features={"odds_observed":True,"price_type":"bookmaker","bookmaker":"book","fair_prob":.50})
    ladder_hard=ph.Prop(player="Ladder Check",market="Hits",odds=2.0,point=1.5,sport="MLB",emoji="⚾",game="A @ B",direction="over",features={"odds_observed":True,"price_type":"bookmaker","bookmaker":"book","fair_prob":.70})
    if any(x.type=="ladder" for x in build_autonomous_extras([], [ladder_easy,ladder_hard],ph.Pick,ph.LadderLeg)): fail("inverted ladder prices accepted")
    ladder_a=ph.Prop(player="Garrett Wilson",market="Receptions",odds=1.55,point=3.5,sport="NFL",emoji="🏈",game="NYJ @ LV",direction="over",features={"odds_observed":True,"price_type":"bookmaker","bookmaker":"betrivers","fair_prob":.76,"gamelog_n":8})
    ladder_b=ph.Prop(player="Garrett Wilson",market="Receptions",odds=2.05,point=4.5,sport="NFL",emoji="🏈",game="NYJ @ LV",direction="over",features={"odds_observed":True,"price_type":"bookmaker","bookmaker":"betrivers","fair_prob":.64,"gamelog_n":8})
    ladder_c=ph.Prop(player="Garrett Wilson",market="Receptions",odds=3.10,point=5.5,sport="NFL",emoji="🏈",game="NYJ @ LV",direction="over",features={"odds_observed":True,"price_type":"bookmaker","bookmaker":"betrivers","fair_prob":.50,"gamelog_n":8})
    good_ladders=[x for x in build_autonomous_extras([], [ladder_a,ladder_b,ladder_c],ph.Pick,ph.LadderLeg) if x.type=="ladder"]
    if not good_ladders or len(good_ladders[0].picks)<2: fail("verified NFL ladder not built")
    core_text=Path("prophunter_core_1391.py").read_text(encoding="utf-8")
    for token in ('return "receptions"','return "receiving_yards"','return "rushing_yards"','return "passing_yards"','return "shots_on_goal"','return "goalie_saves"'):
        if token not in core_text: fail(f"gamelog ladder stat mapping missing: {token}")
    for token in ('MIN_PROB_ANYTIME_TD','MIN_EDGE_ANYTIME_TD','MIN_PROB_2PLUS_TD','MIN_EDGE_2PLUS_TD','MIN_GAMES_TD','rejected["td_sample"]','return "rushing_attempts"','return "targets"'):
        if token not in core_text: fail(f"TD/extended prop lane missing: {token}")
    for token in ('market = str(r.get("market_key") or r.get("market") or "").strip()','direction = str(r.get("direction") or "").strip().lower()','if market == "passing_rushing_yards": continue','direction=direction'):
        if token not in core_text: fail(f"snapshot prop safety missing: {token}")
    nfl_easy=ph.Prop(player="Josh Downs",market="Receptions",odds=1.70,point=2.5,sport="NFL",emoji="🏈",game="IND @ WAS",direction="over",features={"odds_observed":True,"price_type":"bookmaker","bookmaker":"betrivers","fair_prob":.75,"gamelog_n":10})
    nfl_hard=ph.Prop(player="Josh Downs",market="Receptions",odds=2.10,point=3.5,sport="NFL",emoji="🏈",game="IND @ WAS",direction="over",features={"odds_observed":True,"price_type":"bookmaker","bookmaker":"betrivers","fair_prob":.55,"gamelog_n":10})
    nfl_ladders=[x for x in build_autonomous_extras([], [nfl_easy,nfl_hard],ph.Pick,ph.LadderLeg) if x.type=="ladder"]
    if not nfl_ladders or len(nfl_ladders[0].picks)<2: fail("verified NFL alternate ladder missing")
    bad_line=ph.Prop(player="QB",market="Rushing Yards",odds=5.0,point=299.5,sport="NFL",emoji="🏈",game="A @ B",direction="over",features={"odds_observed":True,"price_type":"bookmaker","bookmaker":"book","fair_prob":.25})
    if _plausible_ladder_line(bad_line): fail("implausible NFL ladder line accepted")
    if line_of_pick({"market":"Points Over 20.5"})!=20.5: fail("line fallback")
    if line_of_pick({"market":"Home Run"})!=0.5: fail("binary HR line fallback")
    if line_of_pick({"market":"Anytime TD"})!=0.5: fail("binary TD line fallback")
    if line_of_pick({"market":"Home Run Over 0.5","line":5000})!=0.5: fail("corrupt binary line guard")
    if stat_value({"league":"NFL","passing_tds":3},"passing_touchdowns")!=3: fail("NFL alias")
    if stat_value({"league":"MLB","hits":3,"doubles":1,"triples":0,"home_runs":1},"singles")!=1: fail("MLB singles derivation")
    logs=[{"player_name":"Shohei Ohtani","game_date":"2026-09-18","game_id":"a"},{"player_name":"Shohei Ohtani","game_date":"2026-09-18","game_id":"b"}]
    if find_gamelog({"player":"Shohei Ohtani","commence_time":"2026-09-19T01:00:00Z","market":"Hits Over .5"},logs) is not None: fail("doubleheader ambiguity")
    if not identity_match("Patrick Mahomes II","Patrick Mahomes",threshold=94): fail("identity")
    if not (.70<=source_weight("new-source")<=1.20): fail("source neutral weight")
    if _json_clean({"x":float("nan")})!={"x":None}: fail("json sanitizer")

def main():
    if getattr(ph,"PH_RUNTIME_VERSION",None)!=EXPECTED: fail(f"runtime={getattr(ph,'PH_RUNTIME_VERSION',None)} expected={EXPECTED}")
    source_checks(); safety_checks()
    print("RUNTIME GUARD: keyless DK/FD/Bovada + Kambi/1xBet/keyed parser fixtures OK")
    print("RUNTIME GUARD: quote/player sanity + model/market gap guard OK")
    print("RUNTIME GUARD: no-vig consensus + observed-price/no-synthetic-ladder safety OK")
    print("RUNTIME GUARD: settlement/identity/source-weight safety OK")
    print(f"RUNTIME GUARD OK: {EXPECTED}")
if __name__=="__main__": main()
