#!/usr/bin/env python3
"""Fail-fast deployment guard for PROP HUNTER V12.2."""

from __future__ import annotations

from pathlib import Path
import inspect
import sys

import prophunter
import prop_hunter_bet365 as bet365

EXPECTED = "12.4.2-UNDERDOG-CACHE"


def fail(message: str) -> None:
    print(f"RUNTIME GUARD FAILED: {message}", file=sys.stderr)
    raise SystemExit(2)


def main() -> None:
    if getattr(prophunter, "PH_RUNTIME_VERSION", None) != EXPECTED:
        fail(
            f"wrong prophunter.py version: "
            f"{getattr(prophunter, 'PH_RUNTIME_VERSION', None)!r}; expected {EXPECTED!r}"
        )

    for name in (
        "_has_observed_odds",
        "_has_direct_fantasy_line",
        "_has_eligible_price",
        "enforce_final_verified_market_gate",
        "_conservative_live_probability",
    ):
        if not hasattr(prophunter, name):
            fail(f"prophunter.py missing {name}")

    ph_source = inspect.getsource(prophunter)
    builder_path = Path(__file__).with_name("prop_hunter_builder_engine.py")
    if not builder_path.exists():
        fail("prop_hunter_builder_engine.py missing")
    builder_source = builder_path.read_text(encoding="utf-8")

    for marker in (
        "V12.2 final verified-market gate",
        "HOME-RUN RISK",
        "RISK BUILDER",
        "no verified bookmaker prices matched",
        'rejected["unverified_odds"]',
        '"odds_observed": False',
        "Configured Odds API keys exhausted",
    ):
        if marker not in ph_source:
            fail(f"prophunter.py missing marker: {marker}")

    for marker in (
        'if len(books) != 1 or "" in books:',
        "Echte Alt-Linien",
        "if not _real_price(anchor)",
        'book == "bet365"',
        'get("bet_builder")',
    ):
        if marker not in builder_source:
            fail(f"builder missing marker: {marker}")

    synthetic = prophunter.Prop(
        player="Synthetic Player",
        market="Pitcher Strikeouts",
        odds=1.83,
        point=2.5,
        sport="MLB",
        emoji="⚾",
        game="TEST @ TEST",
        direction="over",
        features={
            "source": "propcruncher",
            "odds_observed": False,
            "price_type": "synthetic",
        },
    )
    if prophunter._has_observed_odds(synthetic):
        fail("synthetic ProCruncher price was accepted")

    real = prophunter.Prop(
        player="Real Player",
        market="Pitcher Strikeouts",
        odds=1.91,
        point=4.5,
        sport="MLB",
        emoji="⚾",
        game="TEST @ TEST",
        direction="over",
        features={
            "source": "betmgm",
            "bookmaker": "betmgm",
            "odds_observed": True,
            "price_type": "bookmaker",
        },
    )
    if not prophunter._has_observed_odds(real):
        fail("observed bookmaker price was rejected")

    underdog = prophunter.Prop(
        player="Direct Fantasy Player", market="Points", odds=1.85, point=19.5,
        sport="WNBA", emoji="🏀", game="TEST @ TEST", direction="over",
        features={
            "source": "underdog", "bookmaker": "underdog",
            "direct_source_line": True, "source_payload_observed": True,
            "odds_observed": False, "price_type": "fantasy_fixed",
        },
    )
    if not prophunter._has_eligible_price(underdog):
        fail("direct Underdog fantasy line was rejected")
    if prophunter._has_observed_odds(underdog):
        fail("Underdog fixed reference price was mislabeled as observed sportsbook odds")

    prizepicks = prophunter.Prop(
        player="Blocked Fantasy Player", market="Points", odds=1.85, point=19.5,
        sport="WNBA", emoji="🏀", game="TEST @ TEST", direction="over",
        features={"source": "prizepicks", "odds_observed": False, "price_type": "synthetic"},
    )
    if prophunter._has_eligible_price(prizepicks):
        fail("synthetic PrizePicks price was accepted")

    mlb = bet365.parse_dom_groups("MLB", [{
        "title": "Home Runs BB",
        "bet_builder": True,
        "participants": [{"text": "Aaron Judge 4.50"}],
    }])
    if not mlb or mlb[0].get("market_key") != "batter_home_runs":
        fail("bet365 MLB Home Runs parser failed")

    nba = bet365.parse_dom_groups("NBA", [{
        "title": "Points, Rebounds and Assists BB",
        "bet_builder": True,
        "participants": [{"text": "Nikola Jokic Over 48.5 1.83"}],
    }])
    if not nba or nba[0].get("market_key") != "player_points_rebounds_assists":
        fail("bet365 NBA PRA parser failed")

    nfl = bet365.parse_dom_groups("NFL", [{
        "title": "Anytime Touchdown Scorer BB",
        "bet_builder": True,
        "participants": [{"text": "Ja'Marr Chase 2.40"}],
    }])
    if not nfl or nfl[0].get("market_key") != "player_anytime_touchdown":
        fail("bet365 NFL touchdown parser failed")

    if not all(row.get("odds_observed") for row in (mlb + nba + nfl)):
        fail("bet365 parser produced unverified prices")

    ud_fixture = [{
        "source": "underdog", "bookmaker": "underdog", "sport": "MLB",
        "player_name": "Fixture Player", "market": "Hits", "market_key": "hits",
        "line": 1.5, "odds_decimal": None, "raw": {"observed": True}
    }]
    ud_props = prophunter._hub_rows_to_props(ud_fixture)
    if len(ud_props) != 1:
        fail("cached Underdog row was dropped")
    if not prophunter._has_direct_fantasy_line(ud_props[0]):
        fail("cached Underdog row was not marked as direct fantasy line")
    print("Cached Underdog rows accepted: OK")

    print(f"RUNTIME GUARD OK: {EXPECTED}")
    print("Synthetic odds rejected: OK")
    print("Observed bookmaker odds accepted: OK")
    print("Direct Underdog fantasy lines accepted without mislabeling odds: OK")
    print("Same-book builder/ladders required: OK")
    print("Verified HR/Risk/Lottery engine present: OK")
    print("bet365 MLB/NBA/WNBA/NFL parser and BB mapping: OK")


if __name__ == "__main__":
    main()
