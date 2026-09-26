#!/usr/bin/env python3
"""Offline regression coverage for all-sports result/settlement expansion."""
from pathlib import Path

from prop_hunter_results_ncaa import parse_ncaab_summary, parse_ncaaf_summary
from prop_hunter_results_mlb_extras import parse_extra_hitting
from prop_hunter_settler_extras import detect_extra_stat, extra_stat_value
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
    check(result_for_value(extra_stat_value(r,"touchdowns"), .5, "over") == "win", "NCAAF TD grading")

def test_mlb_extra():
    split = {
        "date": "2026-09-25",
        "game": {"gamePk": 123},
        "team": {"name": "Team"},
        "opponent": {"name": "Opp"},
        "stat": {"hits": 2, "doubles": 1, "triples": 1, "totalBases": 5, "homeRuns": 0}
    }
    row = parse_extra_hitting("Player X", split, "2026")
    check(row["doubles"] == 1.0 and row["triples"] == 1.0, f"MLB extra parse={row}")
    check(detect_extra_stat("to_hit_a_triple") == "triples", "triple detection")
    check(detect_extra_stat("to_hit_a_double") == "doubles", "double detection")
    check(extra_stat_value({"raw": row["raw"]}, "triples") == 1.0, "raw triple fallback")
    check(result_for_value(1.0, .5, "over") == "win", "triple settlement")

def test_all_sports_sources():
    text = Path("prop_hunter_source_orchestrator.py").read_text(encoding="utf-8")
    for sport in ("MLB","NBA","WNBA","NFL","NHL","NCAAB","NCAAF"):
        check(sport in text, f"{sport} missing source orchestrator")
    workflow = Path(".github/workflows/prophunter_results.yml").read_text(encoding="utf-8")
    for cmd in ("prop_hunter_results_ncaa.py","prop_hunter_results_mlb_extras.py","prop_hunter_settler_extras.py","prop_hunter_learning_update.py"):
        check(cmd in workflow, f"results workflow missing {cmd}")

def main():
    tests=[test_ncaab,test_ncaaf,test_mlb_extra,test_all_sports_sources]
    for t in tests:
        t()
        print(f"EXPANSION TEST OK: {t.__name__}")
    print(f"EXPANSION TEST PASSED: {len(tests)}/{len(tests)} suites")

if __name__ == "__main__":
    main()
