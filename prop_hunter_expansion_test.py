#!/usr/bin/env python3
"""Offline regression coverage for all-sports result/settlement and builder expansion."""
from pathlib import Path

from prop_hunter_results_ncaa import parse_ncaab_summary, parse_ncaaf_summary
from prop_hunter_results_mlb_extras import parse_extra_hitting
from prop_hunter_results_nba import _made as nba_made
from prop_hunter_results_wnba import _made as wnba_made
from prop_hunter_results_nhl import _candidate_name as nhl_candidate_name
from prop_hunter_settler_extras import detect_extra_stat, extra_stat_value, extra_line_of_pick
from prop_hunter_settler import result_for_value


def check(v, msg):
    if not v:
        raise AssertionError(msg)


def test_ncaab():
    payload = {
        "header": {"id": "b1", "competitions": [{"date": "2026-11-10T01:00:00Z"}]},
        "boxscore": {"players": [{
            "team": {"displayName": "Duke"},
            "statistics": [{
                "name": "starters",
                "labels": ["MIN","FG","3PT","FT","OREB","DREB","REB","AST","STL","BLK","TO","PF","PTS"],
                "athletes": [{"athlete": {"displayName": "John Doe"},
                              "stats": ["32","7-12","3-5","2-2","1","5","6","4","2","1","3","2","19"]}]
            }]
        }]}
    }
    rows = parse_ncaab_summary(payload, ["John Doe"])
    check(len(rows) == 1, f"NCAAB rows={rows}")
    r = rows[0]
    check((r["points"], r["rebounds"], r["assists"], r["threes_made"]) == (19.0,6.0,4.0,3.0), f"NCAAB stats={r}")
    check(detect_extra_stat("threes") == "threes_made", "canonical threes settlement")
    check(result_for_value(extra_stat_value(r,"threes_made"), 2.5, "over") == "win", "NCAAB threes grading")


def test_ncaaf():
    payload = {
        "header": {"id": "f1", "competitions": [{"date": "2026-09-26T00:00:00Z"}]},
        "boxscore": {"players": [{
            "team": {"displayName": "Alabama"},
            "statistics": [
                {"name": "passing", "labels": ["C/ATT","YDS","AVG","TD","INT","QBR"],
                 "athletes": [{"athlete": {"displayName": "QB X"}, "stats": ["20/30","250","8.3","3","1","80"]}]},
                {"name": "rushing", "labels": ["CAR","YDS","AVG","TD","LONG"],
                 "athletes": [{"athlete": {"displayName": "QB X"}, "stats": ["8","45","5.6","1","20"]}]},
            ]
        }]}
    }
    rows = parse_ncaaf_summary(payload, ["QB X"])
    check(len(rows) == 1, f"NCAAF rows={rows}")
    r = rows[0]
    check(r["passing_yards"] == 250.0 and r["passing_touchdowns"] == 3.0, f"NCAAF passing={r}")
    check(r["rushing_yards"] == 45.0 and r["rushing_touchdowns"] == 1.0, f"NCAAF rushing={r}")
    check(r["anytime_td"] == 1.0, f"NCAAF TD alias={r}")
    check(detect_extra_stat("2+ touchdowns") == "touchdowns", "generic TD threshold detection")
    check(extra_line_of_pick({"market":"2+ touchdowns"}, "touchdowns") == 1.5, "2+ TD line normalization")
    check(result_for_value(extra_stat_value(r,"touchdowns"), 0.5, "over") == "win", "NCAAF TD grading")


def test_mlb_extra():
    split = {
        "date": "2026-09-25", "game": {"gamePk": 123}, "team": {"name": "Team"},
        "opponent": {"name": "Opp"},
        "stat": {"hits": 2, "doubles": 1, "triples": 1, "totalBases": 5, "homeRuns": 0}
    }
    row = parse_extra_hitting("Player X", split, "2026")
    check(row["doubles"] == 1.0 and row["triples"] == 1.0, f"MLB extra parse={row}")
    check(detect_extra_stat("to_hit_a_triple") == "triples", "triple detection")
    check(detect_extra_stat("to_hit_a_double") == "doubles", "double detection")
    check(extra_line_of_pick({"market":"to_hit_a_triple"}, "triples") == 0.5, "triple line fallback")
    check(extra_stat_value({"raw": row["raw"]}, "triples") == 1.0, "raw triple fallback")
    check(result_for_value(1.0, .5, "over") == "win", "triple settlement")


def test_nba_wnba_nfl_nhl_guards():
    check(nba_made("3-5") == 3.0, "NBA made-attempt parser")
    check(wnba_made("4-9") == 4.0, "WNBA made-attempt parser")
    check(nhl_candidate_name({"name":"Connor McDavid"}) == "Connor McDavid", "NHL identity name")
    check(nhl_candidate_name({"firstName":{"default":"Connor"},"lastName":{"default":"McDavid"}}) == "Connor McDavid", "NHL structured identity name")
    nfl = Path("prop_hunter_results_nfl.py").read_text(encoding="utf-8")
    check("load_schedules" in nfl and '"game_date": game_date' in nfl, "NFL schedule/date mapping missing")
    nba = Path("prop_hunter_results_nba.py").read_text(encoding="utf-8")
    wnba = Path("prop_hunter_results_wnba.py").read_text(encoding="utf-8")
    check("pending_picks" in nba and "espn_pending_logs" in nba, "NBA pending-pick fallback missing")
    check("pending_picks" in wnba and "event_players" in wnba, "WNBA pending-pick path missing")


def test_all_sports_sources():
    text = Path("prop_hunter_source_orchestrator.py").read_text(encoding="utf-8")
    for sport in ("MLB","NBA","WNBA","NFL","NHL","NCAAB","NCAAF"):
        check(sport in text, f"{sport} missing source orchestrator")
    check("prop_hunter_keyless_extensions" in text, "keyless market extension installer missing")
    workflow = Path(".github/workflows/prophunter_results.yml").read_text(encoding="utf-8")
    for cmd in ("prop_hunter_results_ncaa.py","prop_hunter_results_mlb_extras.py","prop_hunter_settler_extras.py","prop_hunter_learning_update.py"):
        check(cmd in workflow, f"results workflow missing {cmd}")
    for key in ("NBA_RESULTS_PLAYER_CAP", "WNBA_RESULT_GAME_CAP", "NFL_RESULTS_PLAYER_CAP", "NHL_RESULTS_PLAYER_CAP"):
        check(key in workflow, f"results runtime bound missing {key}")


def test_builder_profiles_and_market_guard():
    from prop_hunter_quote_guard import canonical_market, sanitize_row
    import prop_hunter_builder_profiles as bp

    check(canonical_market("Double Double") == "double_double", "double-double canonical market")
    check(canonical_market("Rushing Attempts") == "rushing_attempts", "rushing attempts canonical market")
    check(canonical_market("Points + Rebounds") == "pr", "PR canonical market")
    dd = sanitize_row({
        "source":"fixture", "bookmaker":"fanduel", "sport":"NBA", "player_name":"Karl-Anthony Towns",
        "market":"Double Double", "direction":"yes", "line":None, "odds_decimal":1.80,
        "home_team":"Knicks", "away_team":"Pacers", "selection":"Yes",
    })
    check(dd is not None and dd["market"] == "double_double" and dd["line"] == .5, "binary DD line repair")
    check(bp.PROFILE_MAX_LEGS["AGGRESSIVE"] == 10 and bp.PROFILE_MAX_LEGS["LONGSHOT"] == 10, "10-leg builder cap missing")
    check(bp._profile_for_odds(1.90) == "SAFE", "safe profile band")
    check(bp._profile_for_odds(3.00) == "VALUE", "value profile band")
    check(bp._profile_for_odds(8.50) == "AGGRESSIVE", "aggressive profile band")
    check(bp._profile_for_odds(23.37) == "LONGSHOT", "longshot profile band")
    source = Path("prop_hunter_builder_profiles.py").read_text(encoding="utf-8")
    check("same_player_multistat" in source and "max_legs=10" in source, "same-player/10-leg builder logic missing")
    guard = Path("prop_hunter_quote_guard.py").read_text(encoding="utf-8")
    check("_ph_profiles_installed" in guard and "_ph_card_formatter_installed" in guard, "builder/card installer missing")


def test_keyless_extension_and_card_formatter():
    import prop_hunter_keyless_books as kb
    from prop_hunter_keyless_extensions import install as install_keyless
    from prop_hunter_card_formatter import install as install_formatter
    install_keyless(kb)
    check(kb._mk("Rushing Attempts") == "rushing_attempts", "keyless rushing attempts mapping")
    check(kb._mk("Double Double") == "double_double", "keyless double-double mapping")
    check(kb._player_market("Bucky Irving Rushing Attempts") == "Bucky Irving", "DK rushing attempts player parse")
    check(kb._player_market("Tyrese Haliburton Double Double") == "Tyrese Haliburton", "DK double-double player parse")

    class P:
        def __init__(self, **kw): self.__dict__.update(kw)
    p=P(type="betbuilder", market="4-Leg SAFE SGP", odds=2.05, stake=.25, probability=.52, edge_pct=6.6,
        legs=["A 15+ Points @1.20","A 7+ Rebounds @1.20","B 5+ Assists @1.18","C 20+ Points @1.25"],
        features={"builder_profile":"safe","same_player_multistat":True,"builder_odds_estimated_from_legs":True})
    base=lambda picks:"🎯 PROP HUNTER\n\n🎯 BET BUILDER:\n• old @2.05 → 0.25u\n\n📊 Mehr Value Picks\n@prophunter"
    text=install_formatter(base)([p])
    check("🔥 SAME PLAYER SPECIALS:" in text and "Same-Player" in text, "same-player card category missing")
    check("finale Book-Quote bestätigen" in text, "derived SGP quote disclosure missing")

    td=P(type="betbuilder", market="2-Leg SAFE ACCA", odds=4.2, stake=.1, probability=.31, edge_pct=8.0,
        legs=["Josh Allen Anytime TD @2.10","Jalen Hurts Anytime TD @2.00"],
        features={"builder_profile":"safe","combo_scope":"cross_game","acca_odds_estimated_from_legs":True})
    td_text=install_formatter(base)([td])
    check("🏈 TD ACCAS:" in td_text, "TD ACCA category missing")

    dup=P(type="betbuilder", market="4-Leg SAFE SGP", odds=2.05, stake=.25, probability=.52, edge_pct=6.6,
        legs=list(p.legs), features=dict(p.features))
    many=[]
    for i in range(18):
        many.append(P(type="betbuilder", market=f"Long Builder {i}", odds=2.2+i*.1, stake=.1,
            probability=.5, edge_pct=5+i, legs=[f"Player {i} very long observed prop line {j} @1.90" for j in range(1,7)],
            features={"builder_profile":"value","builder_odds_estimated_from_legs":True}))
    long_base=lambda picks:"🎯 PROP HUNTER\n\n"+"\n".join([f"🏀 Player {i}\n   └ Points Over 10.5 @1.90 → 0.2u\n   📈 Edge +5.0% · Prob 60%\n   💡 verbose analysis line {i}" for i in range(12)])+"\n\n🎯 BET BUILDER:\nold\n\n📊 Mehr Value Picks\n@prophunter"
    compact=install_formatter(long_base)([p,dup,*many])
    check(len(compact)<=3950, f"telegram card too long: {len(compact)}")
    check(compact.count("A 15+ Points @1.20")==1, "duplicate builder displayed twice")


def test_delivery_failure_and_team_identity_guards():
    core = Path("prophunter_core_1391.py").read_text(encoding="utf-8")
    check('raise RuntimeError("PROP HUNTER Telegram delivery failed")' in core, "Telegram delivery failure does not fail the card run")
    check('picks NOT persisted' in core, "Telegram failure persistence guard missing")
    start = core.find("def _source_prop_team")
    end = core.find("def _source_prop_game", start)
    block = core[start:end]
    check('getattr(p, "home"' not in block, "player team still falls back to event home team")
    check("_invert_odds" not in core and "p.odds = new_odds" not in core,
          "gamelog enrichment can still synthesize a counter-side price")
    hardened = Path("prophunter_core_1392.py").read_text(encoding="utf-8")
    check('sb.table("prop_hunter_picks").insert(canonical)' in hardened,
          "canonical prop_hunter_picks persistence missing")
    check('sb.table("prop_picks").insert(safe)' in hardened,
          "legacy persistence fallback missing")


def test_supabase_select_rows_paginates():
    shared = Path("prop_hunter_shared_utils.py").read_text(encoding="utf-8")
    check('.range(start, end)' in shared, "Supabase reads are not paginated")
    check('while len(rows) < wanted' in shared, "Supabase pagination loop missing")
    check('return rows[:wanted]' in shared, "Supabase pagination does not honor requested limit")

def test_telegram_ladder_split_contract():
    core = Path("prophunter_core_1391.py").read_text(encoding="utf-8")
    hardened = Path("prophunter_core_1392.py").read_text(encoding="utf-8")
    check("def _telegram_payloads" in core and "def _render_ladder_card" in core,
          "ladder Telegram splitter missing")
    check('send_telegram(body,dry_run=dry_run,picks=picks)' in core,
          "card run does not pass picks to Telegram splitter")
    check('"kind":"ladder"' in core and '"combo_indices":[idx]' in core,
          "ladder cards are not scoped to one combo")
    check('_LAST_TELEGRAM_CARDS' in hardened and '"card_kind": sent.get("kind") or "main"' in hardened,
          "split Telegram cards are not persisted for settlement")
    check('getattr(leg,"probability",None)' in core and 'getattr(leg,"edge_pct",None)' in core,
          "ladder rungs do not display their own probability/edge")
    check("PROP HUNTER TD LADDER" in core and "PROP HUNTER PLAYER LADDER" in core,
          "player/TD ladder card labels missing")
    check("_next_real_line" not in core and "alt_odds = round" not in core,
          "legacy synthetic ladder generator still present")
    check('PH_MAX_HR_SINGLES", "0"' in core,
          "global HR cap default is not disabled")


def test_builder_persistence_and_learning_loop():
    import types
    from prop_hunter_card_formatter import install_persistence
    from prop_hunter_learning_update import learn_builder_correlations

    module=types.SimpleNamespace()
    module.history=[]
    module.log=types.SimpleNamespace(warning=lambda *a, **k: None)

    def base_persist(picks, telegram_message_id=None, telegram_text=None):
        from datetime import datetime, timezone
        today=datetime.now(timezone.utc).strftime("%Y-%m-%d")
        entry=next((e for e in module.history if e["date"]==today),None)
        if entry is None:
            entry={"date":today,"kombis":[]}; module.history.append(entry)
        for pick in picks:
            if getattr(pick,"type",None)=="betbuilder":
                entry["kombis"].append({
                    "type":"betbuilder","market":pick.market,"sport":"NBA","stake":pick.stake,
                    "probability":pick.probability,"result":"pending","leg_details":pick.leg_details,
                })

    module.persist=base_persist
    module.load_history=lambda: module.history
    module.save_history=lambda value: setattr(module,"history",value)
    check(install_persistence(module), "combo persistence overlay did not install")

    class P:
        def __init__(self, **kw): self.__dict__.update(kw)
    legs=[
        {"player":"A","sport":"NBA","market":"Points","direction":"over","probability":.70,"result":"win"},
        {"player":"B","sport":"NBA","market":"Rebounds","direction":"over","probability":.60,"result":"win"},
    ]
    pick=P(type="betbuilder",market="2-Leg SAFE SGP",sport="NBA",stake=.25,probability=.42,
           edge_pct=5.0,ev=.05,game="A @ B",analysis="fixture",leg_details=legs,
           features={"builder_profile":"safe","bookmaker":"fanduel","same_player_multistat":False,
                     "builder_odds_estimated_from_legs":True})
    module.persist([pick])
    row=module.history[0]["kombis"][0]
    check(row["builder_profile"]=="safe" and row["edge_pct"]==5.0, "builder metadata not persisted")
    row["result"]="win"; row["profit"]=.25; row["settlement_legs"]=legs

    module.history[0]["kombis"]=[dict(row) for _ in range(24)]
    learned=learn_builder_correlations(module.history)
    check(learned["profiles"]["safe"]["n"]==24, "builder profile performance missing")
    check(len(learned["pairs"])==1, "builder pair learning missing")
    pair=next(iter(learned["pairs"].values()))
    check(pair["n"]==24 and .85 <= pair["factor"] <= 1.12, "builder pair factor not bounded")


def main():
    tests=[
        test_ncaab,test_ncaaf,test_mlb_extra,test_nba_wnba_nfl_nhl_guards,
        test_all_sports_sources,test_builder_profiles_and_market_guard,
        test_keyless_extension_and_card_formatter,test_delivery_failure_and_team_identity_guards,
        test_supabase_select_rows_paginates,test_telegram_ladder_split_contract,test_builder_persistence_and_learning_loop,
    ]
    for t in tests:
        t(); print(f"EXPANSION TEST OK: {t.__name__}")
    print(f"EXPANSION TEST PASSED: {len(tests)}/{len(tests)} suites")


if __name__ == "__main__":
    main()


# Feature rebuild after large backfills must not issue one giant Supabase UPSERT.
_fb = Path("prop_hunter_feature_builder.py").read_text(encoding="utf-8")
assert "FEATURE_WRITE_BATCH" in _fb
assert "range(0,len(rows),FEATURE_WRITE_BATCH)" in _fb.replace(" ", "").replace("\\n", "")
