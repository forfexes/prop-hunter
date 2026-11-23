"""Offline strict form provenance: each Ladder line owns its gamelog windows.

No remote feed, Telegram send, implied odds or dummy predicted statistics.
"""
import unittest

from prop_hunter_image_cards import _ladder_exact_form

def detail(point, direction, counts, *, same=True):
    x={
        "player":"QA Athlete",
        "point":point,
        "direction":direction,
        "market":f"{direction.title()} {point} Points",
        "features":{
            "gamelog_l15_line":point if same else point+1,
            "gamelog_l15_direction":direction,
            "recent_form":{
                "line":point if same else point+1,
                "direction":direction,
                "l5":{"hits":counts[0],"n":5},
                "l10":{"hits":counts[1],"n":10},
                "l15":{"hits":counts[2],"n":15},
            },
        },
        "gamelog_l15_hits":counts[2],
        "gamelog_l15_n":15,
    }
    return x


class LadderExactForm(unittest.TestCase):
    def test_four_distinct_thresholds_preserve_own_observed_values(self):
        rungs=[
            detail(12.5,"under",(2,5,8)),
            detail(11.5,"under",(3,6,9)),
            detail(8.5,"under",(4,8,11)),
            detail(7.5,"under",(5,9,12)),
        ]
        actual=[_ladder_exact_form(d) for d in rungs]
        self.assertEqual(actual,[
            "L5 2/5 · L10 5/10 · L15 8/15",
            "L5 3/5 · L10 6/10 · L15 9/15",
            "L5 4/5 · L10 8/10 · L15 11/15",
            "L5 5/5 · L10 9/10 · L15 12/15",
        ])
        self.assertEqual(len(set(actual)),4)

    def test_mismatch_line_or_side_never_copies_wrong_stats(self):
        wrong=detail(12.5,"under",(4,9,13),same=False)
        self.assertEqual(_ladder_exact_form(wrong),"L5 — · L10 — · L15 —")
        wrong=detail(12.5,"under",(4,9,13))
        wrong["features"]["recent_form"]["direction"]="over"
        self.assertEqual(_ladder_exact_form(wrong),"L5 — · L10 — · L15 13/15")
        wrong["features"]["gamelog_l15_direction"]="over"
        self.assertEqual(_ladder_exact_form(wrong),"L5 — · L10 — · L15 —")

    def test_real_pick_to_owner_adapter_keeps_each_rung_separate(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from PIL import Image
        import prop_hunter_image_cards as cards

        rows_in=[
            detail(12.5,"under",(2,5,8)),
            detail(11.5,"under",(3,6,9)),
            detail(8.5,"under",(4,8,11)),
            detail(7.5,"under",(5,9,12)),
        ]
        for leg in rows_in:
            leg["sport"]="NBA"
            leg["odds"]=1.82
        # A deliberate old stale-form example: wrong line is NOT copied.
        rows_in[3]["features"]["recent_form"]["line"]=99.5
        pick=SimpleNamespace(type="ladder",source_sport="NBA",
                 game="Denver Nuggets vs Chicago Bulls",
                 player="QA ATHLETE", features={}, odds=1.82,stake=1.0,
                 leg_details=rows_in)
        portrait=Image.new("RGBA",(90,110),(80,110,150,255))
        captured={}
        def fake_adapter(ticket, rows, teams):
            captured["rows"]=rows
            captured["teams"]=teams
            return b"OFFLINE-OWNER-ADAPTER-MOCK"
        with patch("prop_hunter_combo_prices.publishable_extra",
                   return_value=True), \
             patch.object(cards,"league_of",return_value=("basketball","nba")), \
             patch.object(cards,"team_logo",return_value=portrait), \
             patch.object(cards,"player_photo",return_value=portrait), \
             patch("prop_hunter_nba_premium_adapter.render_nba_pick",
                   side_effect=fake_adapter):
            self.assertEqual(cards.build_for_pick(pick),
                             b"OFFLINE-OWNER-ADAPTER-MOCK")
        actual=[row["form"] for row in captured["rows"]]
        self.assertEqual(actual[:3],[
            "L5 2/5 · L10 5/10 · L15 8/15",
            "L5 3/5 · L10 6/10 · L15 9/15",
            "L5 4/5 · L10 8/10 · L15 11/15",
        ])
        self.assertEqual(actual[3],"L5 — · L10 — · L15 12/15")
        self.assertEqual(len(captured["teams"]),2)

    def test_missing_windows_are_unknown_not_extrapolated(self):
        self.assertEqual(_ladder_exact_form({
            "point":11.5,"direction":"over","gamelog_l15_hits":0,
            "gamelog_l15_n":14
        }),"L5 — · L10 — · L15 0/14")
        self.assertEqual(_ladder_exact_form({
            "point":11.5,"direction":"over","gamelog_l15_hits":99,
            "gamelog_l15_n":15
        }),"L5 — · L10 — · L15 —")
        self.assertEqual(_ladder_exact_form({}),
                         "L5 — · L10 — · L15 —")

    def test_reject_bogus_floats_and_wrong_window_counts(self):
        observed=detail(10.5,"over",(3,7,12))
        observed["features"]["recent_form"]["l5"]={"hits":3.5,"n":5}
        observed["features"]["recent_form"]["l10"]={"hits":8,"n":17}
        self.assertEqual(_ladder_exact_form(observed),
                         "L5 — · L10 — · L15 12/15")


if __name__=="__main__":
    unittest.main(verbosity=2)
