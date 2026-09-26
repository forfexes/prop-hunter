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
    check("_ph_profiles_installed" in guard, "builder profile installer missing")


def main():
    tests=[test_ncaab,test_ncaaf,test_mlb_extra,test_nba_wnba_nfl_nhl_guards,test_all_sports_sources,test_builder_profiles_and_market_guard]
    for t in tests:
        t(); print(f"EXPANSION TEST OK: {t.__name__}")
    print(f"EXPANSION TEST PASSED: {len(tests)}/{len(tests)} suites")


if __name__ == "__main__":
    main()
