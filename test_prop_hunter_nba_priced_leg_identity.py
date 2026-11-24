"""NBA owner premium: priced leg identity must equal displayed athlete.

Hermetic QA: never accesses a Telegram bot, network or game-data provider.
"""
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image, ImageDraw
from prop_hunter_nba_premium_adapter import PremiumDataMissing, render_nba_pick


def cutout():
    img=Image.new("RGBA",(110,150),(0,0,0,0))
    ImageDraw.Draw(img).ellipse((20,5,93,82),fill=(130,175,210,255))
    return img


def examples():
    logo=Image.new("RGBA",(90,90),(30,45,80,255))
    teams=[("BOSTON CELTICS",logo),("NEW YORK KNICKS",logo)]
    when=(datetime.now(timezone.utc)+timedelta(days=3)).isoformat()
    common={
        "sport":"NBA","game":"Boston Celtics vs New York Knicks",
        "commence_time":when,"stake":1.0,
        "features":{"bookmaker":"OFFLINE_QA_BOOKMAKER",
                    "combined_odds_observed":True,
                    "combined_quote_id":"OFFLINE-QUOTE-123"}
    }
    rows=[
        {"name":"Jayson Tatum","label":"Points Over 20.5",
         "photo":cutout(),"form":"L5 4/5 L10 8/10 L15 11/15"},
        {"name":"Jaylen Brown","label":"Assists Over 3.5",
         "photo":cutout(),"form":"L5 3/5 L10 7/10 L15 10/15"},
    ]
    ticket=SimpleNamespace(
        **common,type="betbuilder",market="builder",odds=3.88,
        leg_details=[
            {"player":"Jayson Tatum","market":"points","odds":1.85,
             "sport":"NBA","game":common["game"],
             "commence_time":when,"fixture_id":"NBA_QA_SAME_FIXTURE"},
            {"player":"Jaylen Brown","market":"assists","odds":2.12,
             "sport":"NBA","game":common["game"],
             "commence_time":when,"fixture_id":"NBA_QA_SAME_FIXTURE"},
        ])
    return ticket,rows,teams


class NBAPricedLegIdentityQA(unittest.TestCase):
    def test_matching_builder_players_reach_only_owner_bridge(self):
        pick,rows,teams=examples()
        with patch.dict("os.environ",{"PH_NBA_OWNER_ORIGINALS":"1"}), \
             patch("prop_hunter_nba_owner_bridge.render_owner",
                   return_value=b"OFFLINE_OWNER_ONLY") as renderer:
            raw=render_nba_pick(pick,rows,teams)
        self.assertEqual(raw,b"OFFLINE_OWNER_ONLY")
        self.assertEqual(renderer.call_count,1)
        self.assertEqual(renderer.call_args.args[1],"builder_2")

    def test_swapped_athletes_cannot_receive_others_bookmaker_odds(self):
        pick,rows,teams=examples()
        rows[0],rows[1]=rows[1],rows[0]
        with patch.dict("os.environ",{"PH_NBA_OWNER_ORIGINALS":"1"}), \
             patch("prop_hunter_nba_owner_bridge.render_owner") as renderer:
            with self.assertRaisesRegex(PremiumDataMissing,"player identity"):
                render_nba_pick(pick,rows,teams)
        renderer.assert_not_called()

    def test_distinct_players_with_same_surname_are_not_equivalent(self):
        pick,rows,teams=examples()
        pick.leg_details[0]["player"]="Another Tatum"
        with patch.dict("os.environ",{"PH_NBA_OWNER_ORIGINALS":"1"}), \
             patch("prop_hunter_nba_owner_bridge.render_owner") as renderer:
            with self.assertRaisesRegex(PremiumDataMissing,"player identity"):
                render_nba_pick(pick,rows,teams)
        renderer.assert_not_called()

    def test_missing_bookmaker_player_identity_must_never_be_guessed(self):
        pick,rows,teams=examples()
        pick.leg_details[0].pop("player")
        with patch.dict("os.environ",{"PH_NBA_OWNER_ORIGINALS":"1"}), \
             patch("prop_hunter_nba_owner_bridge.render_owner") as renderer:
            with self.assertRaisesRegex(PremiumDataMissing,"no verified bookmaker player identity"):
                render_nba_pick(pick,rows,teams)
        renderer.assert_not_called()

    def test_unicode_accent_is_not_another_athlete(self):
        pick,rows,teams=examples()
        rows[1]["name"]="Jaylén Brown"
        with patch.dict("os.environ",{"PH_NBA_OWNER_ORIGINALS":"1"}), \
             patch("prop_hunter_nba_owner_bridge.render_owner",
                   return_value=b"QA_OWNER_BYTES") as renderer:
            self.assertEqual(render_nba_pick(pick,rows,teams),b"QA_OWNER_BYTES")
        renderer.assert_called_once()

    def test_builder_same_player_wrong_market_is_never_rendered(self):
        pick,rows,teams=examples()
        rows[0]["label"]="Assists Over 20.5"
        with patch.dict("os.environ",{"PH_NBA_OWNER_ORIGINALS":"1"}), \
             patch("prop_hunter_nba_owner_bridge.render_owner") as render:
            with self.assertRaisesRegex(PremiumDataMissing,"market differs"):
                render_nba_pick(pick,rows,teams)
        render.assert_not_called()

    def test_builder_priced_threshold_must_equal_displayed_line(self):
        pick,rows,teams=examples()
        pick.leg_details[0]["point"]=22.5
        with patch.dict("os.environ",{"PH_NBA_OWNER_ORIGINALS":"1"}), \
             patch("prop_hunter_nba_owner_bridge.render_owner") as render:
            with self.assertRaisesRegex(PremiumDataMissing,"threshold differs"):
                render_nba_pick(pick,rows,teams)
        render.assert_not_called()

    def test_builder_priced_over_under_must_equal_displayed_direction(self):
        pick,rows,teams=examples()
        pick.leg_details[1]["direction"]="under"
        with patch.dict("os.environ",{"PH_NBA_OWNER_ORIGINALS":"1"}), \
             patch("prop_hunter_nba_owner_bridge.render_owner") as render:
            with self.assertRaisesRegex(PremiumDataMissing,"direction differs"):
                render_nba_pick(pick,rows,teams)
        render.assert_not_called()

    def test_single_priced_line_and_direction_must_match_display(self):
        pick,rows,teams=examples()
        pick.type="single"
        pick.player="Jayson Tatum"
        pick.market="points"
        pick.direction="under"
        pick.point=20.5
        pick.odds=1.91
        pick.leg_details=[]
        with patch.dict("os.environ",{"PH_NBA_OWNER_ORIGINALS":"1"}), \
             patch("prop_hunter_nba_owner_bridge.render_owner") as render:
            with self.assertRaisesRegex(PremiumDataMissing,"direction differs"):
                render_nba_pick(pick,[rows[0]],teams)
        render.assert_not_called()
        pick.direction="over"
        pick.point=19.5
        with patch.dict("os.environ",{"PH_NBA_OWNER_ORIGINALS":"1"}), \
             patch("prop_hunter_nba_owner_bridge.render_owner") as render:
            with self.assertRaisesRegex(PremiumDataMissing,"threshold differs"):
                render_nba_pick(pick,[rows[0]],teams)
        render.assert_not_called()
        pick.point=20.5
        with patch.dict("os.environ",{"PH_NBA_OWNER_ORIGINALS":"1"}), \
             patch("prop_hunter_nba_owner_bridge.render_owner",
                   return_value=b"UNCHANGED_ORIGINAL_ART") as render:
            self.assertEqual(render_nba_pick(pick,[rows[0]],teams),
                             b"UNCHANGED_ORIGINAL_ART")
        render.assert_called_once()

    def test_different_valid_source_field_alias_line_is_consistent(self):
        pick,rows,teams=examples()
        pick.leg_details[0]["line"]=20.5
        pick.leg_details[0]["direction"]="over"
        pick.leg_details[1]["point"]=3.5
        pick.leg_details[1]["direction"]="over"
        with patch.dict("os.environ",{"PH_NBA_OWNER_ORIGINALS":"1"}), \
             patch("prop_hunter_nba_owner_bridge.render_owner",
                   return_value=b"ORIGINAL") as render:
            self.assertEqual(render_nba_pick(pick,rows,teams),b"ORIGINAL")
        render.assert_called_once()

    def test_market_string_embedded_under_and_line_are_binding(self):
        pick,rows,teams=examples()
        pick.leg_details[0]["market"]="Points Under 20.5"
        with patch.dict("os.environ",{"PH_NBA_OWNER_ORIGINALS":"1"}), \
             patch("prop_hunter_nba_owner_bridge.render_owner") as render:
            with self.assertRaisesRegex(PremiumDataMissing,"direction differs"):
                render_nba_pick(pick,rows,teams)
        render.assert_not_called()
        pick.leg_details[0]["market"]="Points Over 21.5"
        with patch.dict("os.environ",{"PH_NBA_OWNER_ORIGINALS":"1"}), \
             patch("prop_hunter_nba_owner_bridge.render_owner") as render:
            with self.assertRaisesRegex(PremiumDataMissing,"threshold differs"):
                render_nba_pick(pick,rows,teams)
        render.assert_not_called()
        pick.leg_details[0]["market"]="Points Over 20.5"
        with patch.dict("os.environ",{"PH_NBA_OWNER_ORIGINALS":"1"}), \
             patch("prop_hunter_nba_owner_bridge.render_owner",
                   return_value=b"EXACT_ORIGINAL") as render:
            self.assertEqual(render_nba_pick(pick,rows,teams),b"EXACT_ORIGINAL")
        render.assert_called_once()

    def test_single_player_must_match_parent_ticket_identity(self):
        pick,rows,teams=examples()
        pick.type="single"
        pick.market="points"
        pick.player="Jayson Tatum"
        pick.odds=1.87
        pick.leg_details=[]
        with patch.dict("os.environ",{"PH_NBA_OWNER_ORIGINALS":"1"}), \
             patch("prop_hunter_nba_owner_bridge.render_owner") as renderer:
            with self.assertRaisesRegex(PremiumDataMissing,"displayed athlete"):
                render_nba_pick(pick,[rows[1]],teams)
        renderer.assert_not_called()

    def test_single_matching_identity_can_use_approved_original(self):
        pick,rows,teams=examples()
        pick.type="single"
        pick.market="points"
        pick.player="Jayson Tatum"
        pick.odds=1.87
        pick.leg_details=[]
        with patch.dict("os.environ",{"PH_NBA_OWNER_ORIGINALS":"1"}), \
             patch("prop_hunter_nba_owner_bridge.render_owner",
                   return_value=b"OWNER_SINGLE") as renderer:
            self.assertEqual(render_nba_pick(pick,[rows[0]],teams),b"OWNER_SINGLE")
        self.assertEqual(renderer.call_args.args[1],"single_points")


if __name__=="__main__":
    unittest.main(verbosity=2)
