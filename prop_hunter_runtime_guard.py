#!/usr/bin/env python3
from __future__ import annotations

import os

import prophunter as ph
from prop_hunter_builder_engine import build_autonomous_extras
from prop_hunter_identity_hub import identity_match
from prop_hunter_kambi import parse_offer as _kambi_parse
from prop_hunter_oddspapi import TARGETS as _OP_TARGETS, parse_odds_payload as _op_parse
from prop_hunter_oddsapi_io import parse_odds_payload as _oai_parse
from prop_hunter_http import get as _http_get
from prop_hunter_settler import find_gamelog, line_of_pick, stat_value
from prop_hunter_sgo import parse_events as _sgo_parse, _player_name as _sgo_player_name
from prop_hunter_shared_utils import _json_clean
from prop_hunter_source_manager import source_weight

EXPECTED = os.getenv("PH_EXPECTED_RUNTIME_VERSION", "13.9.2-HARDENED-SOURCES-SETTLEMENT")


def fail(msg):
    raise SystemExit(f"RUNTIME GUARD FAILED: {msg}")


def _source_parser_checks():
    sgo_fixture = [{
        "eventID": "sgo-1",
        "startTime": "2026-09-19T23:00:00Z",
        "teams": {
            "home": {"names": {"long": "Los Angeles Lakers"}},
            "away": {"names": {"long": "Boston Celtics"}},
        },
        "odds": {
            "assists-LEBRON_JAMES_1_NBA-game-ou-over": {
                "statID": "assists", "betTypeID": "ou", "statEntityID": "LEBRON_JAMES_1_NBA",
                "sideID": "over", "overUnder": 7.5,
                "byBookmaker": {"draftkings": {
                    "available": True, "overUnder": 7.5, "odds": -110,
                    "altLines": [{"available": True, "overUnder": 8.5, "odds": 120}],
                }},
            }
        },
    }]
    sgo = _sgo_parse(sgo_fixture, "NBA")
    if len(sgo) != 2 or any(r["player_name"] != "Lebron James" or r["direction"] != "over" for r in sgo):
        fail(f"SportsGameOdds fixture/alt-line parse failed: {sgo}")
    if {float(r["line"]) for r in sgo} != {7.5, 8.5}:
        fail(f"SportsGameOdds observed alt lines lost: {sgo}")
    if not any(abs(float(r["odds_decimal"]) - 1.9091) <= 0.001 for r in sgo):
        fail("SportsGameOdds American->decimal conversion failed")
    if any(r.get("commence_time") != "2026-09-19T23:00:00Z" for r in sgo):
        fail("SportsGameOdds startTime parsing regressed")
    if _sgo_player_name("LEBRON_JAMES_1_NBA") != "Lebron James":
        fail("SportsGameOdds v2 numeric player suffix parsing regressed")

    oai_fixture = {
        "id": "oai-1", "home": "Lakers", "away": "Celtics", "date": "2026-09-19T23:00:00Z",
        "league": {"name": "NBA"},
        "bookmakers": {
            "DraftKings": [{
                "name": "Player Props - Points",
                "odds": [{"label": "LeBron James - Points", "hdp": 27.5, "over": 1.91, "under": 1.91}],
            }]
        },
    }
    oai = _oai_parse(oai_fixture, "NBA")
    if len(oai) != 2 or {r["direction"] for r in oai} != {"over", "under"}:
        fail(f"Odds-API.io fixture parse failed: {oai}")
    if any(r["player_name"] != "LeBron James" or float(r["line"]) != 27.5 for r in oai):
        fail("Odds-API.io player/line normalization failed")

    kambi_fixture = {"betOffers": [{
        "criterion": {"label": "Player Points"},
        "outcomes": [
            {"id": "k1", "participant": "LeBron James", "label": "Over 27.5", "line": 27.5, "odds": 1910},
            {"id": "k2", "participant": "LeBron James", "label": "Under 27.5", "line": 27.5, "odds": 1910},
        ],
    }]}
    kambi = _kambi_parse(kambi_fixture, "NBA", "k-event", "Lakers", "Celtics", "2026-09-19T23:00:00Z", "ub")
    if len(kambi) != 2 or {r["direction"] for r in kambi} != {"over", "under"}:
        fail(f"Kambi fixture parse failed: {kambi}")
    if any(abs(float(r["odds_decimal"]) - 1.91) > 0.001 for r in kambi):
        fail("Kambi price normalization failed")


def _settlement_checks():
    if line_of_pick({"point": 20.5, "market": "Points"}) != 20.5:
        fail("settler point field ignored")
    if line_of_pick({"market": "Points Over 20.5"}) != 20.5:
        fail("settler market-line fallback failed")
    if stat_value({"league": "NFL", "passing_tds": 3}, "passing_touchdowns") != 3:
        fail("NFL passing TD legacy alias failed")
    if stat_value({"league": "NHL", "hockey_points": 2}, "points") != 2:
        fail("NHL points alias failed")
    if stat_value({"league": "NHL", "assists_hockey": 1}, "assists") != 1:
        fail("NHL assists alias failed")

    pick = {
        "player": "Shohei Ohtani", "commence_time": "2026-09-19T01:10:00Z",
        "market": "Total Bases Over 1.5", "point": 1.5,
    }
    logs = [
        {"player_name": "Shohei Ohtani", "game_date": "2026-09-12", "game_id": "old"},
        # US-local game date can be one day behind UTC commence timestamp.
        {"player_name": "Shohei Ohtani", "game_date": "2026-09-18", "game_id": "right"},
    ]
    match = find_gamelog(pick, logs)
    if not match or match.get("game_id") != "right":
        fail(f"date-safe settlement matching failed: {match}")
    ambiguous = logs + [{"player_name": "Shohei Ohtani", "game_date": "2026-09-18", "game_id": "doubleheader"}]
    if find_gamelog(pick, ambiguous) is not None:
        fail("ambiguous doubleheader should remain pending")
    if find_gamelog({"player": "Shohei Ohtani", "market": "Hits Over 0.5"}, logs) is not None:
        fail("undated pick must not settle against arbitrary historical game")


def main():
    if getattr(ph, "PH_RUNTIME_VERSION", None) != EXPECTED:
        fail(f"runtime={getattr(ph,'PH_RUNTIME_VERSION',None)} expected={EXPECTED}")

    synthetic = ph.Prop(
        player="Fake", market="Points", odds=1.85, point=20.5, sport="WNBA", emoji="🏀", game="A @ B",
        direction="over", features={"odds_observed": False, "price_type": "synthetic", "bookmaker": "synthetic"},
    )
    if ph._has_observed_price(synthetic):
        fail("synthetic price accepted")
    real = ph.Prop(
        player="Real", market="Points", odds=1.95, point=20.5, sport="WNBA", emoji="🏀", game="A @ B",
        direction="over", features={"odds_observed": True, "price_type": "bookmaker", "bookmaker": "bet365", "fair_prob": 0.60},
    )
    if not ph._has_observed_price(real):
        fail("observed price rejected")

    pick = ph.Pick(type="single", player="Real", market="Points Over 20.5", direction="over", odds=1.95,
                   stake=.2, probability=.60, edge_pct=17, ev=.17, game="A @ B", emoji="🏀")
    pick.point = 20.5
    pick.sport = "WNBA"
    pick.features = real.features
    extras = build_autonomous_extras([pick], [real], ph.Pick, ph.LadderLeg)
    if any(x.type == "ladder" for x in extras):
        fail("ladder invented without observed alternate line")

    if not hasattr(ph, "fetch_nhl_player_gamelogs"):
        fail("NHL gamelog support missing")
    if not all(k in _OP_TARGETS for k in ("baseball_mlb", "basketball_nba", "basketball_wnba", "americanfootball_nfl", "icehockey_nhl")):
        fail("OddsPapi target registry incomplete")
    if not callable(_op_parse) or not callable(_http_get):
        fail("OddsPapi/curl_cffi helpers missing")

    cleaned = _json_clean({"nan": float("nan"), "inf": float("inf"), "nested": [1.0, float("-inf")]})
    if cleaned != {"nan": None, "inf": None, "nested": [1.0, None]}:
        fail("JSON sanitizer failed")
    if not identity_match("Patrick Mahomes II", "Patrick Mahomes", threshold=94):
        fail("identity hub suffix matching failed")
    if not (0.70 <= source_weight("unknown-new-source") <= 1.20):
        fail("source manager neutral weight invalid")

    _source_parser_checks()
    _settlement_checks()

    print("RUNTIME GUARD: source parser fixtures OK")
    print("RUNTIME GUARD: date-safe settlement + NFL/NHL aliases OK")
    print("RUNTIME GUARD: synthetic odds rejected / observed odds accepted OK")
    print("RUNTIME GUARD: no invented ladder from a single line OK")
    print("RUNTIME GUARD: identity/source-weight/JSON sanitizer OK")
    print(f"RUNTIME GUARD OK: {EXPECTED}")


if __name__ == "__main__":
    main()
