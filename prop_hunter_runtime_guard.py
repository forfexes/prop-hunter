#!/usr/bin/env python3
from __future__ import annotations

import inspect
import os
import io
from contextlib import redirect_stdout
from datetime import datetime, timezone, timedelta
from pathlib import Path

import prophunter
import prop_hunter_bet365 as bet365
import prop_hunter_odds_pp_ud as ppud
import prop_hunter_source_orchestrator as orchestrator

EXPECTED = os.getenv("PH_EXPECTED_RUNTIME_VERSION", "12.8-HR-MODEL-123")


def fail(message: str):
    raise SystemExit(f"RUNTIME GUARD FAILED: {message}")


def main():
    if prophunter.PH_RUNTIME_VERSION != EXPECTED:
        fail(f"runtime={prophunter.PH_RUNTIME_VERSION} expected={EXPECTED}")

    required = (
        "_pickem_market_candidates", "_pickem_market_spec_for_prop", "_pickem_row_value",
        "enrich_direct_pickem_prices", "enrich_direct_pickem_gamelogs",
        "rescue_picks_from_props", "enforce_final_verified_market_gate", "build_post", "build_hr_model_card",
    )
    for name in required:
        if not hasattr(prophunter, name):
            fail(f"prophunter.py missing {name}")

    builder_path = Path(__file__).with_name("prop_hunter_builder_engine.py")
    if not builder_path.exists():
        fail("prop_hunter_builder_engine.py missing")
    builder_source = builder_path.read_text(encoding="utf-8")
    for marker in (
        'if len(books) != 1 or "" in books:',
        "Echte Alt-Linien", "if not _real_price(anchor)",
        'book == "bet365"', 'get("bet_builder")',
    ):
        if marker not in builder_source:
            fail(f"builder missing marker: {marker}")

    # Integrity: synthetic prices remain blocked; observed books remain allowed.
    synthetic = prophunter.Prop(
        player="Synthetic", market="Points", odds=1.85, point=20.5, sport="WNBA",
        emoji="🏀", game="A @ B", direction="over",
        features={"source":"propcruncher", "odds_observed":False, "price_type":"synthetic"},
    )
    if prophunter._has_eligible_price(synthetic):
        fail("synthetic price accepted")
    real = prophunter.Prop(
        player="Real", market="Points", odds=1.91, point=20.5, sport="WNBA",
        emoji="🏀", game="A @ B", direction="over",
        features={"source":"bet365", "bookmaker":"bet365", "odds_observed":True, "price_type":"bookmaker"},
    )
    if not prophunter._has_observed_odds(real):
        fail("observed bookmaker price rejected")

    # Realistic Underdog wire fixture: joins player/appearance/game and preserves both choices.
    start = (datetime.now(timezone.utc) + timedelta(minutes=5)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    payload = {
        "players": [{"id":"p1", "first_name":"Fixture", "last_name":"Guard", "sport_id":"WNBA", "position_name":"G", "team_id":"T1"}],
        "appearances": [{"id":"a1", "player_id":"p1", "match_id":182470, "match_type":"Game", "team_id":"T1"}],
        "games": [{"id":182470, "sport_id":"WNBA", "title":"LAS @ NYL", "full_team_names_title":"Los Angeles Sparks @ New York Liberty", "scheduled_at":start, "status":"scheduled"}],
        "solo_games": [],
        "over_under_lines": [{
            "id":"line1", "line_type":"balanced", "live_event":False, "stat_value":"40.5", "status":"active",
            "options":[
                {"choice":"higher", "american_price":"-135", "decimal_price":"1.74", "payout_multiplier":"1.0"},
                {"choice":"lower", "american_price":"+105", "decimal_price":"2.05", "payout_multiplier":"1.0"},
            ],
            "over_under":{"title":"Fixture Guard Fantasy Points O/U", "category":"player_prop",
                          "appearance_stat":{"appearance_id":"a1", "stat":"fantasy_points", "display_stat":"Fantasy Points"}},
        }],
    }
    rows = ppud._parse_underdog_payload(payload)
    if len(rows) != 1:
        fail("Underdog payload parser did not return one row")
    row = rows[0]
    for key in ("commence_time", "source_event_id", "market_key", "higher_odds_decimal", "lower_odds_decimal"):
        if row.get(key) in (None, ""):
            fail(f"Underdog parser lost {key}")
    if row.get("market_key") != "fantasy points" or row.get("price_type") != "pickem_priced":
        fail("Underdog machine market/price type normalization failed")

    db_rows = orchestrator._snapshot_rows_for_db(rows)
    if len(db_rows) != 1 or "higher_odds_decimal" in db_rows[0]:
        fail("Supabase snapshot sanitizer did not remove migration-free fields")
    if not isinstance(db_rows[0].get("raw"), dict) or not db_rows[0]["raw"].get("options"):
        fail("Supabase snapshot sanitizer lost raw Underdog prices")

    american_payload = dict(payload)
    american_payload["over_under_lines"] = [dict(payload["over_under_lines"][0])]
    american_payload["over_under_lines"][0]["options"] = [
        {"choice":"higher", "american_price":"-120"},
        {"choice":"lower", "american_price":"+100"},
    ]
    american_rows = ppud._parse_underdog_payload(american_payload)
    if not american_rows or abs(float(american_rows[0]["higher_odds_decimal"]) - 1.8333333333) > 0.001:
        fail("Underdog American-price fallback failed")

    props = prophunter._hub_rows_to_props(rows)
    if len(props) != 1 or not prophunter._has_direct_fantasy_line(props[0]):
        fail("Underdog cache row rejected by native converter")
    prop = props[0]
    if not prop.commence_time or not prop.game:
        fail("Underdog scheduled matchup did not survive conversion")
    if prophunter._pickem_market_spec_for_prop(prop) is None:
        fail("WNBA Fantasy Points remained unsupported")
    period_prop = prop.model_copy(deep=True)
    period_prop.market = "1H Fantasy Points"
    if prophunter._pickem_market_spec_for_prop(period_prop) is not None:
        fail("period-specific Fantasy Points leaked into full-game model")

    # Official basketball fantasy formula: 20 + 10*1.2 + 5*1.5 + 2*3 + 1*3 - 3 = 45.5.
    basket_spec = prophunter._pickem_market_spec("Fantasy Points", "WNBA")
    basket_value = prophunter._pickem_row_value(
        {"points":20, "rebounds":10, "assists":5, "steals":2, "blocks":1, "turnovers":3},
        basket_spec,
    )
    if basket_value is None or abs(basket_value - 45.5) > 1e-9:
        fail(f"basketball fantasy formula wrong: {basket_value}")

    # Official MLB hitter fantasy formula fixture = 19.
    mlb_spec = prophunter._pickem_market_spec("fantasy_points", "MLB")
    mlb_value = prophunter._pickem_row_value(
        {"total_bases":4, "home_runs":1, "triples":0, "walks_batter":1,
         "hit_by_pitch":0, "rbi":2, "runs":1, "stolen_bases":0}, mlb_spec,
    )
    if mlb_value is None or abs(mlb_value - 19.0) > 1e-9:
        fail(f"MLB fantasy formula wrong: {mlb_value}")

    # Full recent-history model; every current-line market is exercised through the raw machine key.
    history = []
    for i, fp in enumerate((49.1, 46.0, 44.5, 48.0, 47.2, 45.0, 43.5, 46.8, 42.5, 49.0)):
        # Construct rows whose exact formula equals the target approximately.
        history.append({
            "league":"WNBA", "player_name":"Fixture Guard", "normalized_name":"fixture guard",
            "game_date":f"2026-07-{17-i:02d}", "points":25, "rebounds":8, "assists":5,
            "steals":2, "blocks":1, "turnovers": max(0, round(51.1-fp)),
        })
    old_recent = prophunter._recent_pickem_gamelogs
    try:
        prophunter._recent_pickem_gamelogs = lambda leagues: history
        prophunter.enrich_direct_pickem_prices(props)
        prophunter.enrich_direct_pickem_gamelogs(props)
    finally:
        prophunter._recent_pickem_gamelogs = old_recent
    probability = prophunter._fantasy_probability_from_features(prop)
    if probability is None or probability < 0.56:
        fail(f"end-to-end Pick'em probability missing/weak: {probability}")

    picks = prophunter.rescue_picks_from_props(props, max_picks=3)
    picks = prophunter.quality_filter_picks(picks)
    picks = prophunter.enforce_final_verified_market_gate(picks, props)
    if len(picks) != 1:
        fail("qualified Underdog row did not reach final card")
    post = prophunter.build_post(picks)
    if "UNDERDOG PICK'EM" not in post or "@1.85" in post or "Fantasy Points" not in post:
        fail("Telegram Pick'em output mislabeled or missing")

    # Full run must use the deterministic fast lane and skip the LLM when only
    # qualified Pick'em lines are available.
    old_gather, old_analyse = prophunter.gather, prophunter.analyse
    old_send, old_mode = prophunter.send_telegram, prophunter.PH_CARD_MODE
    sent = []
    try:
        prophunter.gather = lambda sport_filter=None: props
        prophunter.analyse = lambda _: fail("LLM called despite Pick'em-only card")
        prophunter.send_telegram = lambda body, dry_run=False: sent.append(body)
        prophunter.PH_CARD_MODE = "all"
        with redirect_stdout(io.StringIO()):
            prophunter.run(dry_run=True)
    finally:
        prophunter.gather, prophunter.analyse = old_gather, old_analyse
        prophunter.send_telegram, prophunter.PH_CARD_MODE = old_send, old_mode
    if len(sent) != 1 or "UNDERDOG PICK'EM" not in sent[0] or "@1.85" in sent[0]:
        fail("Pick'em fast lane did not produce a clean Telegram post")

    # Scheduled card split must retain the parsed kickoff.
    kept = prophunter.filter_props_for_card(props, "all", now_utc=datetime.now(timezone.utc))
    if len(kept) != 1:
        fail("parsed Underdog kickoff was dropped by scheduled card filter")

    # Known standard/machine labels across all four requested sports.
    aliases = (
        ("pts_rebs_asts", "WNBA"), ("three_pointers_made", "NBA"),
        ("pitcher_strikeouts", "MLB"), ("hits_runs_rbis", "MLB"),
        ("passing_yards", "NFL"), ("rushing_receiving_yards", "NFL"),
    )
    for market, sport in aliases:
        if prophunter._pickem_market_spec(market, sport) is None:
            fail(f"market alias unsupported: {sport}/{market}")

    # Bet365 parser remains intact across active sports.
    mlb = bet365.parse_dom_groups("MLB", [{"title":"Home Runs BB", "bet_builder":True, "participants":[{"text":"Aaron Judge 4.50"}]}])
    nba = bet365.parse_dom_groups("NBA", [{"title":"Points, Rebounds and Assists BB", "bet_builder":True, "participants":[{"text":"Nikola Jokic Over 48.5 1.83"}]}])
    nfl = bet365.parse_dom_groups("NFL", [{"title":"Anytime Touchdown Scorer BB", "bet_builder":True, "participants":[{"text":"Ja'Marr Chase 2.40"}]}])
    if not mlb or mlb[0].get("market_key") != "batter_home_runs":
        fail("bet365 MLB parser regression")
    if not nba or nba[0].get("market_key") != "player_points_rebounds_assists":
        fail("bet365 NBA parser regression")
    if not nfl or nfl[0].get("market_key") != "player_anytime_touchdown":
        fail("bet365 NFL parser regression")
    if not all(row.get("odds_observed") for row in (mlb + nba + nfl)):
        fail("bet365 parser produced unverified prices")

    try:
        prophunter.Pick(type="lottery", odds=3.0, stake=0.1, legs=["A", "B"])
    except Exception as exc:
        fail(f"lottery Pick schema rejected: {exc}")

    # HR model 1-2-3 fixture: one single, one double, one triple; no fake book price in Telegram.
    hr_cache = {
        "mlb": {
            "batters_basic": {
                "alpha slugger": {"player_name":"Alpha Slugger", "team_name":"Team A", "games":80, "pa":340, "hr":25, "avg":0.280, "slg":0.590, "ops":0.960},
                "beta power": {"player_name":"Beta Power", "team_name":"Team B", "games":82, "pa":350, "hr":23, "avg":0.275, "slg":0.565, "ops":0.925},
                "gamma bat": {"player_name":"Gamma Bat", "team_name":"Team C", "games":79, "pa":330, "hr":21, "avg":0.268, "slg":0.545, "ops":0.900},
            },
            "pitchers_basic": {
                "pitcher b": {"player_name":"Pitcher B", "hr9":1.45},
                "pitcher a": {"player_name":"Pitcher A", "hr9":1.35},
                "pitcher d": {"player_name":"Pitcher D", "hr9":1.30},
            },
            "lineups": {
                "team a": {"team_name":"Team A", "opponent_team":"Team B", "opponent_probable_pitcher":"Pitcher B", "game_date":start, "status":"Scheduled"},
                "team b": {"team_name":"Team B", "opponent_team":"Team A", "opponent_probable_pitcher":"Pitcher A", "game_date":start, "status":"Scheduled"},
                "team c": {"team_name":"Team C", "opponent_team":"Team D", "opponent_probable_pitcher":"Pitcher D", "game_date":start, "status":"Scheduled"},
            },
        }
    }
    hr_model = prophunter.build_hr_model_card(hr_cache)
    if [getattr(p, "category", "") for p in hr_model] != ["hr_model_single", "hr_model_double", "hr_model_triple"]:
        fail(f"HR model 1-2-3 structure wrong: {[getattr(p, 'category', '') for p in hr_model]}")
    hr_post = prophunter.build_post(hr_model)
    for required_text in ("HR MODELL-CARD", "SINGLE", "DOUBLE", "TRIPLE", "ohne bestätigte Bookmakerquote"):
        if required_text not in hr_post:
            fail(f"HR model Telegram missing {required_text}")
    if "@" in "\n".join(line for line in hr_post.splitlines() if "SINGLE" in line or "DOUBLE" in line or "TRIPLE" in line):
        fail("HR model card displayed a bookmaker price")

    # Full run must post the HR card even when no sportsbook/Pick'em source returns rows.
    old_gather = prophunter.gather
    old_hr_builder = prophunter.build_hr_model_card
    old_send = prophunter.send_telegram
    old_persist = prophunter.persist
    hr_sent = []
    persisted = []
    try:
        prophunter.gather = lambda sport_filter=None: []
        prophunter.build_hr_model_card = lambda cache_data=None: hr_model
        prophunter.send_telegram = lambda body, dry_run=False: hr_sent.append(body)
        prophunter.persist = lambda rows: persisted.extend(rows)
        with redirect_stdout(io.StringIO()):
            prophunter.run(dry_run=False)
    finally:
        prophunter.gather = old_gather
        prophunter.build_hr_model_card = old_hr_builder
        prophunter.send_telegram = old_send
        prophunter.persist = old_persist
    if len(hr_sent) != 1 or "HR MODELL-CARD" not in hr_sent[0]:
        fail("HR-only run did not post")
    if persisted:
        fail("model-only HR card was persisted as a priced wager")

    workflow = (Path(__file__).parent / ".github/workflows/prophunter.yml").read_text(encoding="utf-8")
    for marker in (
        "PH_EXPECTED_RUNTIME_VERSION: '12.8-HR-MODEL-123'",
        "PROP_HUNTER_SPORTS: MLB,WNBA,NBA,NFL",
        "PH_FAST_BROWSER_BOOKS: bet365",
        "PH_FAST_BROWSER_JOBS: '2'",
        "PH_ENABLE_PROPCRUNCHER: '0'",
        "PH_ENABLE_SLOW_ENRICHMENTS: '0'",
    ):
        if marker not in workflow:
            fail(f"workflow missing marker: {marker}")
    if "PROP_HUNTER_SPORTS: MLB,WNBA,NBA,NFL,NHL" in workflow:
        fail("NHL still enabled")
    orchestrator_source = inspect.getsource(orchestrator)
    if '"league": ",".join(spec["sports"]) or "ALL"' not in orchestrator_source:
        fail("source registry league fallback missing")
    if '"PH_FAST_BROWSER_BOOKS", "bet365"' not in orchestrator_source or '"PH_FAST_BROWSER_JOBS", "2"' not in orchestrator_source:
        fail("orchestrator fast browser defaults are not minute-safe")

    source = inspect.getsource(prophunter)
    for marker in (
        "V12.8 final market gate", "slow web/synthetic enrichments disabled",
        "enrich_direct_pickem_prices", "Pick'em fast lane",
        "build_hr_model_card", "HR model card posted but not persisted as bookmaker wager",
    ):
        if marker not in source:
            fail(f"runtime source missing {marker}")

    print("Underdog payload join and two-sided prices: OK")
    print("WNBA/MLB official Fantasy Points scoring: OK")
    print("Underdog cache -> scoring -> quality -> final gate -> Telegram: OK")
    print("Pick'em-only fast lane skips LLM: OK")
    print("Scheduled card kickoff preservation: OK")
    print("MLB/NBA/WNBA/NFL market alias coverage: OK")
    print("Synthetic odds rejected: OK")
    print("Observed bookmaker odds accepted: OK")
    print("Slow dead-source chain disabled: OK")
    print("Supabase snapshot schema compatibility: OK")
    print("Source registry league fallback: OK")
    print("Same-book builder/ladders required: OK")
    print("Lottery Pick schema: OK")
    print("bet365 MLB/NBA/NFL parser preserved: OK")
    print("HR model single/double/triple without fake odds: OK")
    print("HR-only card posts without sportsbook rows: OK")
    print(f"RUNTIME GUARD OK: {EXPECTED}")


if __name__ == "__main__":
    main()
