#!/usr/bin/env python3
"""Offline HARD TEST for PROP HUNTER production paths.

No API keys, Telegram messages, browser sessions or Supabase writes are performed.
The test exercises parsers, pick persistence, snapshot direction, settlement safety,
inline Telegram rendering, schema drift recovery and runtime/browser guards.
"""
from __future__ import annotations

import builtins
import json
import os
import sys
import tempfile
import types
from datetime import datetime, timezone
from pathlib import Path


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


def test_runtime_guard():
    import prop_hunter_runtime_guard as rg
    rg.main()


def test_snapshot_direction_and_persist():
    import prophunter as ph

    class Result:
        def __init__(self, data): self.data = data
    class Query:
        def __init__(self, data): self.data = data
        def select(self, *a, **k): return self
        def gte(self, *a, **k): return self
        def limit(self, *a, **k): return self
        def execute(self): return Result(self.data)
    class SB:
        def __init__(self, data): self.data = data
        def table(self, *a, **k): return Query(self.data)

    row = {
        "sport": "NBA", "league": "NBA", "source_event_id": "evt-1",
        "player_name": "LeBron James", "market": "player_points", "market_key": "player_points",
        "direction": "under", "line": 27.5, "odds_decimal": 1.91,
        "commence_time": "2026-09-19T23:00:00Z", "created_at": datetime.now(timezone.utc).isoformat(),
        "home_team": "Lakers", "away_team": "Celtics", "bookmaker": "draftkings", "source": "fixture",
    }
    old_sb = ph._sb_read
    ph._sb_read = lambda: SB([row])
    try:
        props = ph.fetch_snapshot_props("NBA")
    finally:
        ph._sb_read = old_sb
    check(len(props) == 1, f"snapshot conversion expected 1 row, got {len(props)}")
    check(props[0].direction == "under", "snapshot stored direction was not preserved")
    check(props[0].features.get("source_event_id") == "evt-1", "snapshot event id lost")
    check(props[0].commence_time is not None, "snapshot commence time lost")

    with tempfile.TemporaryDirectory() as td:
        old_hist, old_insert = ph.HISTORY_FILE, ph.sb_insert
        captured = []
        ph.HISTORY_FILE = str(Path(td) / "picks_history.json")
        ph.sb_insert = lambda r: captured.append(dict(r))
        try:
            p = ph.Pick(type="single", player="LeBron James", team="Lakers", market="Points Over 27.5",
                        direction="over", odds=1.91, stake=1.0, probability=.61, game="Celtics @ Lakers")
            p.point = 27.5
            p.source_sport = "NBA"
            p.commence_time = datetime(2026, 9, 19, 23, 0, tzinfo=timezone.utc)
            p.features = {"source": "sportsgameodds", "bookmaker": "draftkings", "source_event_id": "evt-99"}
            ph.persist([p])
            hist = json.loads(Path(ph.HISTORY_FILE).read_text())
        finally:
            ph.HISTORY_FILE, ph.sb_insert = old_hist, old_insert
        saved = hist[0]["picks"][0]
        check(saved.get("point") == 27.5 and saved.get("line") == 27.5, "pick line not persisted structurally")
        check(saved.get("event_id") == "evt-99", "event id not persisted")
        check(saved.get("raw", {}).get("commence_time"), "commence time not preserved in raw pick")
        check(captured and captured[0].get("bookmaker") == "draftkings", "bookmaker not passed to DB row")


def test_schema_drift_upsert():
    import prop_hunter_shared_utils as su

    class State:
        calls = 0
        final = None
    state = State()

    class Query:
        def __init__(self, payload): self.payload = payload
        def execute(self):
            state.calls += 1
            if state.calls == 1:
                raise Exception("{'code':'PGRST204','message':\"Could not find the 'rush_attempts' column\"}")
            if state.calls == 2:
                raise Exception("{'code':'PGRST204','message':\"Could not find the 'passing_tds' column\"}")
            state.final = self.payload
            return types.SimpleNamespace(data=[])
    class Table:
        def upsert(self, payload, on_conflict=None): return Query(payload)
        def insert(self, payload): return Query(payload)
    class SB:
        def table(self, name): return Table()

    old = su.supabase_client
    su.supabase_client = lambda: SB()
    try:
        rows = [
            {"sport":"NFL","league":"NFL","season":"2026","game_id":"event-only","normalized_name":"", "raw":{}},
            {"sport":"NFL","league":"NFL","season":"2026","game_id":"g1","normalized_name":"player x","player_name":"Player X","rush_attempts":4,"passing_tds":1,"receiving_yards":10},
            {"sport":"NFL","league":"NFL","season":"2026","game_id":"g1","normalized_name":"player x","player_name":"Player X","rush_attempts":5,"passing_tds":2,"receiving_yards":20},
        ]
        su.upsert_rows("prop_hunter_player_gamelogs", rows, "sport,league,season,game_id,normalized_name")
    finally:
        su.supabase_client = old
    check(state.calls == 3, f"schema drift retries expected 3 calls, got {state.calls}")
    check(state.final and len(state.final) == 1, "event-only row / duplicate conflict row not removed")
    check("rush_attempts" not in state.final[0] and "passing_tds" not in state.final[0], "missing schema fields not stripped iteratively")
    check(state.final[0].get("receiving_yards") == 20, "dedupe did not keep latest row")


def test_no_playwright_when_disabled():
    import prop_hunter_http as phhttp
    import prop_hunter_odds_pp_ud as pp

    os.environ["PH_BROWSER_ENABLED"] = "0"

    class Resp:
        status_code = 403
        def json(self): return {}
    class Scraper:
        def get(self, *a, **k): return Resp()
    fake_cloud = types.ModuleType("cloudscraper")
    fake_cloud.create_scraper = lambda: Scraper()

    old_cloud = sys.modules.get("cloudscraper")
    old_get = phhttp.get
    old_import = builtins.__import__
    touched = {"playwright": False}
    def guarded_import(name, *args, **kwargs):
        if name.startswith("playwright"):
            touched["playwright"] = True
            raise AssertionError("Playwright import attempted with PH_BROWSER_ENABLED=0")
        return old_import(name, *args, **kwargs)
    sys.modules["cloudscraper"] = fake_cloud
    phhttp.get = lambda *a, **k: Resp()
    builtins.__import__ = guarded_import
    try:
        result = pp._pp_json("https://fixture.invalid/projections")
    finally:
        builtins.__import__ = old_import
        phhttp.get = old_get
        if old_cloud is None:
            sys.modules.pop("cloudscraper", None)
        else:
            sys.modules["cloudscraper"] = old_cloud
    check(result is None, "blocked PrizePicks fixture unexpectedly returned data")
    check(not touched["playwright"], "Playwright was touched on a lean card path")


def test_source_fallback_chain_and_browser_gate():
    import prop_hunter_source_orchestrator as orch

    os.environ["PH_BROWSER_ENABLED"] = "0"
    os.environ["PH_DIRECT_ROWS_PER_SPORT_TARGET"] = "20"
    called = {"oai": 0, "kambi": 0, "browser": 0}
    def real_rows():
        return [{
            "source":"sportsgameodds", "bookmaker":"draftkings", "sport":"MLB", "league":"MLB",
            "source_event_id":f"e{i}", "player_name":f"Player {i}", "market":"hits", "direction":"over",
            "line":0.5 + i, "odds_decimal":1.9,
        } for i in range(25)]
    def oai(): called["oai"] += 1; raise AssertionError("Odds-API.io should have been skipped after enough SGO coverage")
    def kambi(): called["kambi"] += 1; raise AssertionError("Kambi should have been skipped after enough SGO coverage")
    def browser(*a, **k): called["browser"] += 1; raise AssertionError("browser jobs should be disabled")

    old = {
        "direct": orch._direct_jobs, "browser": orch._browser_jobs, "upsert": orch.upsert_rows,
        "persist": orch.persist_registry, "write": orch.safe_json_write,
    }
    orch._direct_jobs = lambda sports: [
        ("sportsgameodds_mlb", real_rows), ("oddsapi_io_mlb", oai), ("kambi_mlb", kambi), ("underdog", lambda: [])
    ]
    orch._browser_jobs = browser
    orch.upsert_rows = lambda *a, **k: None
    orch.persist_registry = lambda: None
    orch.safe_json_write = lambda *a, **k: None
    try:
        rows = orch.collect("MLB", "fast")
    finally:
        orch._direct_jobs, orch._browser_jobs, orch.upsert_rows = old["direct"], old["browser"], old["upsert"]
        orch.persist_registry, orch.safe_json_write = old["persist"], old["write"]
    check(len(rows) == 25, f"coverage chain expected 25 rows, got {len(rows)}")
    check(called == {"oai":0,"kambi":0,"browser":0}, f"fallback/browser calls leaked: {called}")


def test_mlb_result_normalization():
    import prop_hunter_results_mlb as mlb
    from prop_hunter_settler import stat_value
    split = {
        "date":"2026-09-18", "isHome": True, "game":{"gamePk":123},
        "team":{"abbreviation":"LAD"}, "opponent":{"abbreviation":"SF"},
        "stat":{"hits":2,"totalBases":5,"homeRuns":1,"rbi":2,"runs":1,"strikeOuts":0,"baseOnBalls":1,"stolenBases":0},
    }
    hit = mlb.parse_hitting("Shohei Ohtani", split, "2026")
    check(hit["game_id"] == "123" and hit["total_bases"] == 5, "MLB hitter normalization failed")
    psplit = dict(split)
    psplit["stat"] = {"strikeOuts":8,"inningsPitched":"6.2","hits":4,"earnedRuns":2,"baseOnBalls":1,"homeRuns":1}
    pit = mlb.parse_pitching("Pitcher X", psplit, "2026")
    check(stat_value(pit, "pitcher_outs") == 20, f"MLB innings->outs settlement failed: {stat_value(pit,'pitcher_outs')}")
    merged = mlb.merge_rows([hit, {**hit, "rbi":3}])
    check(len(merged) == 1 and merged[0]["rbi"] == 3, "MLB result dedupe/merge failed")


def test_inline_same_post_render():
    import prophunter_results as pr
    pick = {
        "dedup_key":"lebron|points|27.5|over", "player":"LeBron James", "market":"Points Over 27.5",
        "point":27.5, "direction":"over", "odds":1.91, "stake":1.0,
        "result":"win", "actual_value":32, "profit":0.91,
    }
    card = {
        "text":"🎯 PROP HUNTER\nLeBron James\n└ Points Over 27.5 @1.91 · 1.0u\n\n@prophunter",
        "pick_keys":[pick["dedup_key"]], "combo_ids":[],
    }
    text = pr._decorate_card(card, [pick], [])
    check(text is not None, "inline reporter failed to edit fixture card")
    check("✅" in text and "Ergebnis 32" in text and "+0.91u" in text, f"inline settlement missing details: {text}")
    check("🏁 Auswertung:" in text, "inline card summary missing")


def test_no_synthetic_ladder():
    import prophunter as ph
    p = ph.Pick(type="single", player="Player X", team="X", market="Points Over 20.5", direction="over",
                odds=1.90, stake=1.0, probability=.62, edge_pct=17, game="A @ B")
    p.point = 20.5
    p.features = {"odds_observed":True,"price_type":"bookmaker","bookmaker":"book"}
    extras = ph.build_jk_extras([p])
    check(not any(getattr(x, "type", "") == "ladder" for x in extras), "legacy synthetic ladder was still generated")


def test_workflow_wiring():
    card = Path('.github/workflows/prophunter.yml').read_text()
    results = Path('.github/workflows/prophunter_results.yml').read_text()
    maintenance = Path('.github/workflows/prop_hunter_maintenance.yml').read_text()
    check("13.9.2-HARDENED-SOURCES-SETTLEMENT" in card, "card runtime guard version stale")
    check("python prophunter_results.py" in card, "inline reporter missing from card settlement path")
    check("ODDSAPI_IO_KEY" in card and "PH_KAMBI_ENABLED: '1'" in card, "new source fallback env missing")
    check("ODDSPAPI: ${{ secrets.ODDSPAPI }}" in card, "legacy OddsPapi secret alias not exported")
    check("PH_BDL_PROPS_ENABLED: '0'" in card, "known plan-gated BDL prop endpoint is still enabled")
    check(card.count("PH_BROWSER_ENABLED: '0'") >= 1, "browser not disabled in lean source path")
    check("prop_hunter_results_mlb.py" in results and Path("prop_hunter_results_mlb.py").exists(), "MLB results file/workflow mismatch")
    check("Public snapshot connectors" not in card, "redundant duplicate source sweep still present in card workflow")
    check("settler soft-fail; card continues" in card and "source orchestrator soft-fail" in card,
          "optional pre-card maintenance can still block tip generation")
    check("13.9.2-HARDENED-SOURCES-SETTLEMENT" in maintenance, "maintenance runtime guard version stale")
    # The Odds API must stay event-wise for player props, never use Gemini's invalid all-sport props pattern.
    src = Path("prophunter.py").read_text()
    check('/events/{eid}/odds' in src, "The Odds API player-prop event endpoint regressed")



def test_scoring_and_builder_learning_modules():
    import prop_hunter_scoring as scoring
    import prop_hunter_builder_learning as bl

    prop = types.SimpleNamespace(
        player="Shohei Ohtani", sport="MLB", market="Home Run Over 0.5",
        odds=4.50, point=0.5, features={}
    )
    data = {
        "mlb": {
            "batters_basic": {
                "shohei ohtani": {"ab": 100, "hr": 8, "slg": 0.600, "ops": 0.950}
            }
        }
    }
    out = scoring.apply_data_plus_to_props([prop], data)
    check(out and out[0] is prop, "DATA+ scoring did not preserve prop")
    check("data_plus_score" in prop.features, "DATA+ scoring feature missing")
    check(prop.features.get("fair_prob") is not None, "DATA+ scoring fair probability missing")
    key1 = bl.pair_key("points:over", "assists:over")
    key2 = bl.pair_key("assists:over", "points:over")
    check(key1 == key2, "builder-learning pair key is not order-stable")
    check(bl.market_group("Player Passing Touchdowns") == "passing_touchdowns", "builder-learning market normalization failed")

def main():
    tests = [
        test_runtime_guard,
        test_snapshot_direction_and_persist,
        test_schema_drift_upsert,
        test_no_playwright_when_disabled,
        test_source_fallback_chain_and_browser_gate,
        test_mlb_result_normalization,
        test_inline_same_post_render,
        test_no_synthetic_ladder,
        test_workflow_wiring,
        test_scoring_and_builder_learning_modules,
    ]
    for fn in tests:
        fn()
        print(f"HARD TEST OK: {fn.__name__}")
    print(f"HARD TEST PASSED: {len(tests)}/{len(tests)} suites")


if __name__ == "__main__":
    main()
