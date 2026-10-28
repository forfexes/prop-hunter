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
    nhl = Path("prop_hunter_results_nhl.py").read_text(encoding="utf-8")
    mlb = Path("prop_hunter_results_mlb.py").read_text(encoding="utf-8")
    check("pending_picks" in nba and "espn_pending_logs" in nba, "NBA pending-pick fallback missing")
    check("pending_picks" in wnba and "event_players" in wnba, "WNBA pending-pick path missing")
    check("def _event_final" in wnba and "not _event_final(ev)" in wnba, "WNBA final-game guard missing")
    check("sorted(by_date.items(), key=_date_priority)" in wnba, "WNBA recent-result prioritization missing")
    check("/api/v1/search/player" in nhl and "'type':'player'" not in nhl, "NHL current player-search endpoint missing")
    check("PH_MLB_RESULTS_LOOKBACK_DAYS" in mlb and "rows.sort(" in mlb, "MLB unresolved-card prioritization missing")
    check('"gameType": game_type' in mlb and 'for game_type in ("R", "P")' in mlb, "MLB postseason gamelog fetch missing")
    settler = Path("prop_hunter_settler.py").read_text(encoding="utf-8")
    reporter = Path("prophunter_results.py").read_text(encoding="utf-8")
    check("_pick_ready_for_settlement" in settler and "start_dt.hour < 7" in settler,
          "settler can still grade future/wrong-date games")
    check("oldest_pending = min(dates)" in settler and "start = oldest_pending - timedelta(days=1)" in settler,
          "historical pending settlement is still clamped to recent lookback")
    check("persist_settlements(settled)" in settler and "settlement mirror failed" in settler,
          "verified settlements are not mirrored back to source pick status")
    check("_reset_premature_result" in reporter and "_settlement_ready_time" in reporter,
          "Telegram reporter cannot undo premature settlements")


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
    p=P(type="betbuilder", market="2-Leg SAFE SGP", odds=2.05, stake=.25, probability=.52, edge_pct=6.6,
        legs=["A 15+ Points @1.20","A 7+ Rebounds @1.20"],
        features={"builder_profile":"safe","same_player_multistat":True,"builder_odds_estimated_from_legs":True})
    base=lambda picks:"🎯 PROP HUNTER\n\n🎯 BET BUILDER:\n• old @2.05 → 0.25u\n\n📊 Mehr Value Picks\n@prophunter"
    text=install_formatter(base)([p])
    check("🔥 SAME PLAYER SPECIALS:" in text and "Same-Player" in text, "same-player card category missing")
    check("Keine synthetische Kombiquote/EV ausgegeben" in text, "derived SGP quote disclosure missing")
    check("@2.05 → 0.25u" not in text, "derived combined price still shown as placeable quote")

    td=P(type="betbuilder", market="2-Leg SAFE ACCA", odds=4.2, stake=.1, probability=.31, edge_pct=8.0,
        legs=["Josh Allen Anytime TD @2.10","Jalen Hurts Anytime TD @2.00"],
        features={"builder_profile":"safe","combo_scope":"cross_game","acca_odds_estimated_from_legs":True})
    td_text=install_formatter(base)([td])
    check("🏈 TD ACCAS:" in td_text, "TD ACCA category missing")
    check("@4.20" not in td_text and "Keine synthetische Kombiquote/EV ausgegeben" in td_text,
          "derived ACCA price still shown as real quote")

    mixed=P(type="betbuilder", market="4-Leg LONGSHOT SGP", odds=100, stake=.05, probability=.04, edge_pct=300,
        legs=["A Points @2.0","B Rebounds @2.0","A Assists @2.0","C Points @2.0"],
        features={"builder_profile":"longshot","same_player_multistat":False,"builder_odds_estimated_from_legs":True})
    mixed_text=install_formatter(base)([mixed])
    check("SAME PLAYER SPECIALS" not in mixed_text and "Same-Player" not in mixed_text,
          "mixed-player builder mislabeled as same-player")

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
    check('"pick_type": src.get("pick_type") or src.get("type") or "single"' in hardened,
          "canonical persistence still forces every pick to single")
    check('"legs": src.get("legs") or []' in hardened and 'ladder_legs' in hardened,
          "ladder/combo legs are not persisted canonically")
    settler = Path("prop_hunter_settler.py").read_text(encoding="utf-8")
    extras = Path("prop_hunter_settler_extras.py").read_text(encoding="utf-8")
    check('hash_key("pick", pid)' in settler and 'hash_key("pick", pid)' in extras,
          "settlement ids are not unique per pick")
    check('sb.table("prop_picks").insert(safe)' in hardened,
          "legacy persistence fallback missing")


def test_supabase_select_rows_paginates():
    shared = Path("prop_hunter_shared_utils.py").read_text(encoding="utf-8")
    check('.range(start, end)' in shared, "Supabase reads are not paginated")
    check('while wanted is None or len(rows) < wanted' in shared, "Supabase pagination loop missing")
    check('q = q.order(order_by, desc=desc)' in shared, "Supabase pagination lacks deterministic ordering")
    check('return rows if wanted is None else rows[:wanted]' in shared,
          "Supabase pagination does not support full reads and requested limits")

def test_telegram_pro_tip_window_contract():
    core = Path("prophunter_core_1391.py").read_text(encoding="utf-8")
    hardened = Path("prophunter_core_1392.py").read_text(encoding="utf-8")
    check("def _telegram_payloads" in core and "def _render_ladder_card" in core,
          "PRO TIP Telegram splitter missing")
    check('send_telegram(body,dry_run=dry_run,picks=picks)' in core,
          "card run does not pass picks to Telegram splitter")
    check('"kind":"single"' in core and '"single_indices":[idx]' in core,
          "single PRO TIP windows do not keep exact pick scope")
    check('"combo_indices":[idx]' in core and 'one tip = one window' in core,
          "combo/ladder PRO TIP windows do not keep exact settlement scope")
    check('_LAST_TELEGRAM_CARDS' in hardened and '"card_kind": sent.get("kind") or "main"' in hardened,
          "split Telegram cards are not persisted for settlement")
    check('getattr(leg,"probability",None)' in core and 'getattr(leg,"edge_pct",None)' in core,
          "ladder rungs do not display their own probability/edge")
    check("PROP HUNTER TD LADDER" in core and "PROP HUNTER PLAYER LADDER" in core,
          "player/TD ladder card labels missing")
    check("_next_real_line" not in core and "alt_odds = round" not in core,
          "legacy synthetic ladder generator still present")
    check("PH_TELEGRAM_429_RETRIES" in core and "retry_after" in core and "PH_TELEGRAM_SEND_DELAY" in core,
          "Telegram 429 retry/backoff missing")
    check("PH_TELEGRAM_MAX_PAYLOADS" not in core and "Telegram payload cap" not in core,
          "qualified PRO TIP windows must not be silently capped")
    builder = Path("prop_hunter_builder_engine.py").read_text(encoding="utf-8")
    check("PH_MAX_LADDERS" in builder and "selected_keys" in builder and "selected=selected" in builder,
          "ladder generation is not bounded to selected card ideas")
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


def test_binary_enrichment_and_cross_game_pool():
    core = Path("prophunter_core_1391.py").read_text(encoding="utf-8")
    acca = Path("prop_hunter_acca_engine.py").read_text(encoding="utf-8")
    builder = Path("prop_hunter_builder_engine.py").read_text(encoding="utf-8")
    check('if point is None and stat not in ("double_double", "triple_double")' in core,
          "binary DD/TD enrichment is blocked by the numeric-line guard")
    check('stat in ("double_double", "triple_double")' in core and 'gamelog_dd_rate' in core,
          "binary DD/TD enrichment missing")
    check('"triple_double"' in acca and 'event_options: Dict[str, List[Any]]' in acca,
          "cross-game DD/TD alternative search missing")
    check('len(event_options[game]) < 4' in acca and '_compatible' in acca,
          "bounded per-event alternatives / event compatibility missing")
    check('extras.extend(_real_ladders(props, PickCls, LadderLegCls, selected=selected))' in builder,
          "independent observed-quote ladder lane missing")



def test_odds_api_observed_sides():
    core = Path("prophunter_core_1391.py").read_text(encoding="utf-8")
    assert '"side_prices":{"over":[],"under":[]}' in core
    assert 'for direction,prices in rec["side_prices"].items()' in core
    assert 'direction=direction' in core
    assert '1.0-fair_over' in core


def main():
    tests=[
        test_ncaab,test_ncaaf,test_mlb_extra,test_nba_wnba_nfl_nhl_guards,
        test_all_sports_sources,test_builder_profiles_and_market_guard,
        test_keyless_extension_and_card_formatter,test_delivery_failure_and_team_identity_guards,
        test_supabase_select_rows_paginates,test_telegram_pro_tip_window_contract,test_builder_persistence_and_learning_loop,
        test_binary_enrichment_and_cross_game_pool,test_odds_api_observed_sides,
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

# Source-prop event scoping must fail closed; never borrow a same-name prop from another game.
core_src=Path("prophunter_core_1391.py").read_text(encoding="utf-8")
assert 'if not scoped:\n            return None' in core_src
wnba_src=Path("prop_hunter_results_wnba.py").read_text(encoding="utf-8")
assert 'return matched >= 2' in wnba_src
print("EVENT SCOPE FAIL-CLOSED TEST PASSED")

# NFL/NHL ladders are dedicated lanes and must not depend on winning the Single slot.
assert 'sport == "NHL"' in builder
assert 'sport == "NFL"' in builder
assert '"shots on goal", "goalie saves", "points", "assists", "goals"' in builder
assert '"passing yards", "rushing yards", "receiving yards", "receptions"' in builder
assert '"passing touchdowns", "rushing touchdowns", "receiving touchdowns", "touchdowns"' in builder
assert 'and not dedicated_ladder' in builder

# Normal card: strongest qualified Single per player; raw props stay intact for extras.
assert 'def prioritize_best_single_per_player(picks):' in core
assert 'return (observed,prob,l15,min(n,15),edge)' in core
assert 'picks = prioritize_best_single_per_player(picks)' in core
assert 'build_autonomous_extras(picks, props, Pick, LadderLeg)' in core

# NHL requests explicit alternate market keys so real ladder rungs can enter the raw pool.
for key in ("player_shots_on_goal_alternate","player_goals_alternate","player_points_alternate","player_assists_alternate","player_goalie_saves_alternate"):
    assert key in core
