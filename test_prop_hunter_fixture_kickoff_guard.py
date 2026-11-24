"""Offline regressions for incorrect 01:11 NBA kickoff on real-match cards."""
from __future__ import annotations

import ast
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from prop_hunter_fixture_time_guard import kickoff_comparison, mark_official_conflict
import prop_hunter_matchup as schedule
from prop_hunter_image_publication_gate import pre_match_quote_provenance

WRONG = "2026-11-25T00:11:00+00:00"
OFFICIAL = "2026-11-25T00:00:00Z"
MATCH = "DET Pistons @ ORL Magic"
CORE = Path(__file__).resolve().with_name("prophunter_core_1391.py")


def extracted(name, scope):
    tree = ast.parse(CORE.read_text(encoding="utf-8"))
    matches = [node for node in tree.body if isinstance(node, ast.FunctionDef)
               and node.name == name]
    if len(matches) != 1:
        raise AssertionError("Production function changed: " + name)
    code = compile(ast.fix_missing_locations(ast.Module(
        body=matches, type_ignores=[])), str(CORE), "exec")
    exec(code, scope)
    return scope[name]


class KickoffGuardTest(TestCase):
    def test_exact_same_fixture_different_start_is_blocked(self):
        schedule._SCHED["NBA"] = {}
        schedule._FIXTURE_STARTS["NBA"] = {
            ("DET", "ORL"): [OFFICIAL],
            ("BOS", "NYK"): ["2026-11-25T01:30:00Z"],
        }
        self.assertEqual(schedule.official_fixture_start("NBA",MATCH,WRONG), OFFICIAL)
        self.assertEqual(kickoff_comparison(WRONG, OFFICIAL), "conflict")
        self.assertEqual(kickoff_comparison(OFFICIAL, OFFICIAL), "match")

    def test_only_full_verified_nba_pair_can_match(self):
        schedule._SCHED["NBA"] = {}
        schedule._FIXTURE_STARTS["NBA"] = {("DET","ORL"): [OFFICIAL]}
        for game in ("DET Pistons @ NY Knicks", "DET", "Detroit @ Orlando",
                     "Unknown Team @ Orlando Magic"):
            with self.subTest(game=game):
                self.assertIsNone(schedule.official_fixture_start("NBA",game,WRONG))
        self.assertIsNone(schedule.official_fixture_start("NHL",MATCH,WRONG))

    def test_ambiguous_repeat_games_and_distant_matches_not_guessed(self):
        schedule._SCHED["NBA"] = {}
        schedule._FIXTURE_STARTS["NBA"] = {
            ("DET","ORL"): [OFFICIAL, "2026-11-25T04:00:00Z"]}
        self.assertIsNone(schedule.official_fixture_start("NBA",MATCH,WRONG))
        schedule._FIXTURE_STARTS["NBA"] = {
            ("DET","ORL"): ["2026-12-01T00:00:00Z"]}
        self.assertIsNone(schedule.official_fixture_start("NBA",MATCH,WRONG))

    def test_marked_conflict_preserves_original_raw_start_and_price(self):
        pick = SimpleNamespace(commence_time=WRONG, odds=1.70,
                               features={"bookmaker":"book","odds_observed":True})
        self.assertEqual(mark_official_conflict(pick,OFFICIAL),"conflict")
        self.assertEqual(pick.commence_time,WRONG)
        self.assertEqual(pick.odds,1.70)
        self.assertIs(pick.features["verified_fixture_kickoff_conflict"], True)

    def test_invalid_timezone_is_not_claimed_as_independent_proof(self):
        for invalid in ("2026-11-25T01:11:00","bad", None):
            self.assertEqual(kickoff_comparison(invalid,OFFICIAL),"unverified")

    def test_production_pre_match_gate_refuses_confirmed_discrepancy(self):
        start=(datetime.now(timezone.utc)+timedelta(days=2)).isoformat()
        good=SimpleNamespace(type="single",odds=1.82,commence_time=start,
                             features={"odds_observed":True,"bookmaker":"verified"})
        self.assertTrue(pre_match_quote_provenance(good)[0])
        bad=SimpleNamespace(**vars(good))
        bad.features={**good.features,"verified_fixture_kickoff_conflict":True}
        self.assertEqual(pre_match_quote_provenance(bad),
                         (False,"official_fixture_kickoff_conflict"))

    def test_production_enrichment_marks_conflict_not_rewrites_start(self):
        logs=SimpleNamespace(info=lambda *a:None,warning=lambda *a:None)
        scope={"datetime":datetime,"log":logs}
        fn=extracted("enrich_commence",scope)
        pick=SimpleNamespace(sport="NBA",game=MATCH,commence_time=WRONG,
                             features={},odds=1.70)
        with patch.object(schedule,"official_fixture_start",return_value=OFFICIAL), \
             patch.object(schedule,"game_start",return_value=OFFICIAL), \
             patch.object(schedule,"game_venue",return_value=None):
            out=fn([pick])
        self.assertEqual(len(out),1)
        self.assertIs(out[0],pick)
        self.assertEqual(pick.commence_time,WRONG)
        self.assertTrue(pick.features.get("verified_fixture_kickoff_conflict"))
