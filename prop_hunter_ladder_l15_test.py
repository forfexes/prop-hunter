#!/usr/bin/env python3
"""Regression tests for fail-closed, line-specific PROP HUNTER ladders."""
import unittest
from types import SimpleNamespace
from prop_hunter_builder_engine import (
    _ladder_leg_candidate, _real_ladders, _wilson_l15_lower_bound,
)


def prop(player, market, line, odds, n, hits, model_prob, *, side="over",
         game="A @ B", book="fanduel", sport="NHL", with_history=True):
    features = {
        "odds_observed": True, "price_type": "bookmaker",
        "bookmaker": book, "fair_prob": model_prob,
    }
    if with_history:
        features.update({
            "gamelog_l15_n": n, "gamelog_l15_hits": hits,
            "gamelog_l15_line": line, "gamelog_l15_direction": side,
            "gamelog_l15_empirical_rate": hits / n,
        })
    return SimpleNamespace(
        player=player, market=market, point=line, odds=odds,
        probability=model_prob, direction=side, game=game,
        sport=sport, features=features, emoji="🏒",
    )


class DummyPick:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class TestLadderL15(unittest.TestCase):
    def test_mackinnon_three_goals_zero_of_twelve_rejected(self):
        p = prop("Nathan MacKinnon", "goals", 2.5, 46.0, 12, 0, .0304)
        self.assertIsNone(_ladder_leg_candidate(p))

    def test_mackinnon_two_goals_weak_conservative_value_rejected(self):
        p = prop("Nathan MacKinnon", "goals", 1.5, 9.5, 12, 2, .1237)
        self.assertIsNone(_ladder_leg_candidate(p))

    def test_mackinnon_seven_sog_three_of_twelve_not_certain_value(self):
        p = prop("Nathan MacKinnon", "shots_on_goal", 6.5, 7.5, 12, 3, .1817)
        self.assertIsNone(_ladder_leg_candidate(p))

    def test_mackinnon_one_sog_twelve_of_twelve_can_pass(self):
        p = prop("Nathan MacKinnon", "shots_on_goal", .5, 1.3774, 12, 12, .8409)
        c = _ladder_leg_candidate(p)
        self.assertIsNotNone(c)
        self.assertLessEqual(c["probability"], _wilson_l15_lower_bound(12, 12))

    def test_howard_zero_thirty_rejected(self):
        p = prop("Rhyne Howard", "points", 29.5, 29.0, 15, 0, .0371, sport="WNBA")
        self.assertIsNone(_ladder_leg_candidate(p))

    def test_howard_twentyfive_two_hits_not_guaranteed_positive_ev(self):
        p = prop("Rhyne Howard", "points", 24.5, 10.4, 15, 2, .1062, sport="WNBA")
        self.assertIsNone(_ladder_leg_candidate(p))

    def test_jordin_eight_assists_nine_hits_can_pass(self):
        p = prop("Jordin Canada", "assists", 7.5, 2.72, 15, 9, .5023, sport="WNBA")
        c = _ladder_leg_candidate(p)
        self.assertIsNotNone(c)
        self.assertGreater(c["edge"], .03)

    def test_absent_history_and_mismatched_line_fail_closed(self):
        p = prop("Nathan MacKinnon", "shots_on_goal", .5, 1.38, 12, 12, .84,
                 with_history=False)
        self.assertIsNone(_ladder_leg_candidate(p))
        p = prop("Nathan MacKinnon", "shots_on_goal", .5, 1.38, 12, 12, .84)
        p.features["gamelog_l15_line"] = 6.5
        self.assertIsNone(_ladder_leg_candidate(p))
        p.features["gamelog_l15_line"] = .5
        p.features["gamelog_l15_direction"] = "under"
        self.assertIsNone(_ladder_leg_candidate(p))

    def test_insufficient_games_or_one_hit_rejected(self):
        self.assertIsNone(_ladder_leg_candidate(
            prop("Test Player", "points", 19.5, 4.0, 9, 9, .7)))
        self.assertIsNone(_ladder_leg_candidate(
            prop("Test Player", "points", 29.5, 100.0, 15, 1, .03)))

    def test_unverified_odds_rejected(self):
        p = prop("Test Player", "points", 14.5, 2.0, 15, 13, .8)
        p.features["odds_observed"] = False
        self.assertIsNone(_ladder_leg_candidate(p))

    def test_no_single_rung_masquerades_as_ladder(self):
        a = prop("Nathan MacKinnon", "shots_on_goal", .5, 1.3774, 12, 12, .8409)
        b = prop("Nathan MacKinnon", "shots_on_goal", 6.5, 7.5, 12, 3, .1817)
        self.assertEqual(_real_ladders([a, b], DummyPick, DummyPick), [])

    def test_under_push_not_counted_as_win(self):
        p = prop("Test Player", "points", 1, 2.5, 15, 10, .7, side="under")
        self.assertIsNotNone(_ladder_leg_candidate(p))
        p.features["gamelog_l15_direction"] = "over"
        self.assertIsNone(_ladder_leg_candidate(p))


if __name__ == "__main__":
    unittest.main()
