"""Block false displayed combined prices on all NBA owner-original cards.

All input is synthetic and permanently disconnected from Telegram.
A multiplied leg product (even if numerically plausible) is NOT a real
bookmaker ticket; all parlay formats require observed bookmaker provenance.
"""
import io
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image, ImageDraw

import prop_hunter_nba_owner_bridge as bridge
import prop_hunter_owner_clean_builder as builder
from prop_hunter_original_compositor import _source


def logo():
    image=Image.new("RGBA",(80,80),(0,0,0,0))
    ImageDraw.Draw(image).rectangle((15,5,65,75),fill=(230,168,38,255))
    return image


def athlete():
    image=Image.new("RGBA",(120,150),(0,0,0,0))
    ImageDraw.Draw(image).ellipse((10,10,100,140),fill=(77,113,200,255))
    return image


class RealTicketOnly(unittest.TestCase):
    def setUp(self):
        self.teams=[("QA HOME",logo()),("QA AWAY",logo())]
        self.rows=[dict(name="QA ATHLETE "+str(n),
                        label="QA MARKET",photo=athlete(),form="",
                        result="",odds="@1.90") for n in range(2)]
        self.values=dict(date="23.11.2026",time="20:00",
                         stake="1u",total_odds="62.40",
                         leg_1_odds="@1.90",leg_2_odds="@1.95",
                         leg_1_game="QA HOME vs QA AWAY 20:00",
                         leg_2_game="QA HOME vs QA AWAY 20:30",
                         settlement="OFFEN")

    def test_no_multi_leg_family_may_show_calculated_price(self):
        for key in ("builder_2","lottery_2","same_player_2"):
            with self.subTest(key=key):
                pick=SimpleNamespace(type="betbuilder",features={
                    "price_type":"calculated_from_leg_odds",
                    "builder_odds_estimated_from_legs":True,
                    "combined_odds_observed":True,
                    "combined_quote_id":"STORED_STALE_ID"})
                with patch.dict(os.environ,{
                     "PH_NBA_OWNER_ORIGINALS":"1",
                     "PH_BLOCK_OVERPAINTED_MASTERS":"1",
                     "PH_ALLOW_VERIFIED_LAYERED_OWNER":"1"}), patch.object(
                         bridge,"_layered_owner_release_ready",return_value=True):
                    with self.assertRaisesRegex(ValueError,"calculated quote forbidden"):
                        bridge.render_owner(pick,key,self.rows,self.teams,self.values,[])

    def test_direct_builder_cannot_style_multiplied_odds_as_real_quote(self):
        with patch("prop_hunter_original_compositor._background_portrait",
                   return_value=True):
            with self.assertRaisesRegex(ValueError,"not an observed bookmaker"):
                builder.render(_source("builder"),
                               subtitle="QA HOME vs QA AWAY · Mo 23.11.2026 · 20:00",
                               teams=self.teams,rows=self.rows,
                               footer="Berechnet 62.40 · Einsatz 1u",
                               settlement="OFFEN")

    def test_formula_preview_is_explicit_and_never_prints_bookmaker_total(self):
        pick=SimpleNamespace(type="betbuilder",features={})
        env={"PH_NBA_OWNER_ORIGINALS":"1", "PH_NBA_FORMULA_OFFLINE_QA":"1"}
        self.values["leg_1_odds"] = "@2.00"
        for key, renderer in (("builder_2", builder), ("lottery_2",
                           __import__("prop_hunter_owner_clean_lottery")),
                           ("cross_game_2", __import__("prop_hunter_owner_clean_lottery"))):
            with self.subTest(key=key), patch.dict(os.environ,env,clear=True), patch.object(
                    renderer, "_text", wraps=renderer._text) as printed:
                result=bridge.render_owner(pick,key,self.rows,self.teams,self.values,[],
                                           formula_preview=True)
                self.assertTrue(result.startswith(bytes((137,80,78,71))))
                strings=[str(call.args[2]) for call in printed.call_args_list]
                self.assertIn("3.90",strings)
                self.assertTrue(any("KEINE BOOKIE-QUOTE" in v for v in strings))
                self.assertNotIn("@62.40",strings)
                self.assertNotIn("BUCHMACHER-QUOTE",strings)
        with patch.dict(os.environ,{"PH_NBA_OWNER_ORIGINALS":"1"},clear=True):
            with self.assertRaisesRegex(ValueError,"isolated offline QA"):
                bridge.render_owner(pick,"builder_2",self.rows,self.teams,
                                    self.values,[],formula_preview=True)

    def test_verified_builder_ticket_reaches_original_renderer_not_estimate(self):
        pick=SimpleNamespace(type="betbuilder",features={
            "combined_odds_observed":True,
            "combined_quote_id":"TEST_BOOKMAKER_RECEIPT_77",
            "bookmaker":"TEST ONLY"})
        actual=io.BytesIO()
        Image.new("RGB",(1080,1280),(5,14,26)).save(actual,"PNG")
        with patch.dict(os.environ,{
                "PH_NBA_OWNER_ORIGINALS":"1",
                "PH_BLOCK_OVERPAINTED_MASTERS":"1",
                "PH_ALLOW_VERIFIED_LAYERED_OWNER":"1"}), patch.object(
                    bridge,"_layered_owner_release_ready",return_value=True), patch(
                    "prop_hunter_original_compositor.original_card",
                    return_value=actual.getvalue()) as render:
            result=bridge.render_owner(pick,"builder_2",self.rows,
                                       self.teams,self.values,[])
            self.assertEqual(result[:8],bytes((137,80,78,71,13,10,26,10)))
            footer=render.call_args.args[6]
            self.assertIn("Quote 62.40",footer)
            self.assertNotIn("Berechnet",footer)


if __name__=="__main__":
    unittest.main(verbosity=2)
