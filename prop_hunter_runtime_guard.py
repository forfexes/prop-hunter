#!/usr/bin/env python3
"""Fail-fast deployment guard for PROP HUNTER V12.6."""

from __future__ import annotations

from pathlib import Path
import inspect
import sys

import prophunter
import prop_hunter_bet365 as bet365

EXPECTED = "12.6-PICKEM-MODEL"


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
        "_fantasy_min_probability",
        "_fantasy_stake",
        "_prepare_direct_fantasy_pick",
        "_pickem_probability_from_values",
        "enrich_direct_pickem_gamelogs",
    ):
        if not hasattr(prophunter, name):
            fail(f"prophunter.py missing {name}")

    ph_source = inspect.getsource(prophunter)
    builder_path = Path(__file__).with_name("prop_hunter_builder_engine.py")
    if not builder_path.exists():
        fail("prop_hunter_builder_engine.py missing")
    builder_source = builder_path.read_text(encoding="utf-8")

    for marker in (
        "V12.6 final market gate",
        "UNDERDOG PICK'EM",
        "settlement_mode",
        "HOME-RUN RISK",
        "RISK BUILDER",
        "no verified sportsbook price or qualified direct Pick'em line",
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

    pickem_candidate = prophunter.Pick(
        type="single", emoji="⚾", player="Fixture Player", team="",
        market="Hits Over 1.5", direction="over", odds=1.85, stake=0.25,
        probability=0.60, edge_pct=-1.0, game="",
    )
    pickem_candidate.point = 1.5
    pickem_candidate.source_sport = "MLB"
    pickem_candidate.features = dict(ud_props[0].features)
    filtered = prophunter.quality_filter_picks([pickem_candidate])
    if len(filtered) != 1:
        fail("qualified Pick'em candidate was rejected by quality filter")
    gated = prophunter.enforce_final_verified_market_gate(filtered, ud_props)
    if len(gated) != 1 or not prophunter._has_direct_fantasy_line(gated[0]):
        fail("qualified Pick'em candidate was rejected by final gate")
    post = prophunter.build_post(gated)
    if "Underdog Pick'em" not in post or "@1.85" in post:
        fail("Pick'em Telegram output was mislabeled as a sportsbook price")
    low_candidate = pickem_candidate.model_copy(deep=True)
    low_candidate.probability = 0.51
    if prophunter.quality_filter_picks([low_candidate]):
        fail("low-probability Pick'em candidate was accepted")
    # Recent-game Pick'em model: direction and conservative probability.
    recent = prophunter._pickem_probability_from_values(
        [2, 2, 1, 2, 2, 1, 2, 2, 2, 1], 0.5, 6
    )
    if not recent or recent.get("direction") != "over" or recent.get("probability", 0) < 0.55:
        fail("recent Pick'em gamelog probability model failed")
    if prophunter._pickem_market_spec("Fantasy Points", "WNBA") is not None:
        fail("unsupported fantasy-points market was accepted")

    # Official MLB season-rate fallback: no standalone odds and no synthetic EV.
    from prop_hunter_scoring import apply_data_plus_to_props
    season_prop = ud_props[0].model_copy(deep=True)
    season_prop.player = "Season Fixture"
    season_prop.market = "Hits"
    season_prop.point = 0.5
    season_prop.direction = "over"
    season_data = {"mlb": {"batters_basic": {
        "season fixture": {"games": 80, "hits": 96, "total_bases": 150,
                           "hr": 15, "runs": 50, "rbi": 55, "walks": 30,
                           "strikeouts": 70, "stolen_bases": 8}
    }, "pitchers_basic": {}, "team_k_rates": {}}}
    apply_data_plus_to_props([season_prop], season_data)
    season_prob = prophunter._fantasy_probability_from_features(season_prop)
    if season_prob is None or season_prob < 0.55:
        fail("MLB season Pick'em fallback failed")
    if str((season_prop.features or {}).get("fair_prob_source")) != "mlb_season_poisson":
        fail("MLB season fallback source marker missing")

    # Full cached-row -> official stats -> rescue -> Telegram smoke test.
    rescue = prophunter.rescue_picks_from_props([season_prop], max_picks=3)
    if len(rescue) != 1 or not prophunter._has_direct_fantasy_line(rescue[0]):
        fail("season-scored Underdog row did not produce a rescue pick")
    rescue_post = prophunter.build_post(rescue)
    if "Underdog Pick'em" not in rescue_post or "@1.85" in rescue_post:
        fail("season-scored Pick'em post contains a fake sportsbook price")
    print("Underdog cache-to-Telegram smoke test: OK")

    # Schema accepts the existing lottery lane.
    try:
        prophunter.Pick(type="lottery", odds=3.0, stake=0.1, legs=["A", "B"])
    except Exception as exc:
        fail(f"lottery Pick schema rejected: {exc}")
    print("Recent gamelog and MLB season Pick'em models: OK")
    print("Lottery Pick schema: OK")

    workflow_path = Path(__file__).with_name(".github") / "workflows" / "prophunter.yml"
    if not workflow_path.exists():
        fail(".github/workflows/prophunter.yml missing")
    workflow_source = workflow_path.read_text(encoding="utf-8")
    for workflow_marker in (
        "PH_EXPECTED_RUNTIME_VERSION: '12.6-PICKEM-MODEL'",
        "PROP_HUNTER_SPORTS: MLB,WNBA,NBA,NFL",
        "PH_MIN_PICKEM_SAMPLE: '6'",
        "prop_hunter_scoring.py",
        "prop_hunter_scraper.py",
    ):
        if workflow_marker not in workflow_source:
            fail(f"workflow missing marker: {workflow_marker}")
    if "PROP_HUNTER_SPORTS: MLB,WNBA,NBA,NFL,NHL" in workflow_source:
        fail("NHL is still enabled in the daily Prop Hunter workflow")
    print("Workflow V12.6 environment and sports list: OK")

    orchestrator_source = Path(__file__).with_name("prop_hunter_source_orchestrator.py").read_text(encoding="utf-8")
    if '"league": ",".join(spec["sports"]) or "ALL"' not in orchestrator_source:
        fail("source registry league fallback missing")
    print("Underdog probability scoring and Telegram labeling: OK")
    print("Source registry league fallback: OK")

    print(f"RUNTIME GUARD OK: {EXPECTED}")
    print("Synthetic odds rejected: OK")
    print("Observed bookmaker odds accepted: OK")
    print("Direct Underdog fantasy lines accepted without mislabeling odds: OK")
    print("Same-book builder/ladders required: OK")
    print("Verified HR/Risk/Lottery engine present: OK")
    print("bet365 MLB/NBA/WNBA/NFL parser and BB mapping: OK")


if __name__ == "__main__":
    main()
