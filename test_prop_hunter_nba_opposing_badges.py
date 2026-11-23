"""Block duplicated opposing NBA badges before an original Telegram card.

Offline only: no ESPN network calls, external odds or Telegram credentials.
"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image, ImageDraw

import prop_hunter_image_cards as cards


def crest(rgb, padding=0):
    size=60+padding*2
    img=Image.new("RGBA",(size,size),(0,0,0,0))
    ImageDraw.Draw(img).ellipse((padding+5,padding+5,
                                padding+54,padding+54),fill=(*rgb,255))
    return img


class NBADuplicateCrestQA(unittest.TestCase):
    def test_visible_badge_identity_ignores_transparent_margins(self):
        a=crest((180,35,49))
        same=crest((180,35,49),padding=45)
        different=crest((14,110,194))
        self.assertTrue(cards._same_visible_team_crest(
            [("HOME",a),("AWAY",same)]))
        self.assertFalse(cards._same_visible_team_crest(
            [("HOME",a),("AWAY",different)]))
        self.assertFalse(cards._same_visible_team_crest(
            [("HOME",None),("AWAY",different)]))

    def test_production_image_pipeline_rejects_two_matching_crests(self):
        pick=SimpleNamespace(
            type="single",source_sport="NBA",player="QA TEST PLAYER",
            market="points",direction="under",point=10.5,odds=1.78,
            game="Denver Nuggets vs Chicago Bulls",features={},
            probability=.7,edge_pct=11.0)
        a=crest((180,35,49))
        b=crest((14,110,194))
        with patch("prop_hunter_combo_prices.publishable_extra",
                   return_value=True), \
             patch.object(cards,"league_of",
                          return_value=("basketball","nba")), \
             patch.object(cards,"player_photo",return_value=a), \
             patch("prop_hunter_nba_premium_adapter.render_nba_pick",
                   return_value=b"QA_ONLY") as renderer:
            with patch.object(cards,"team_logo",return_value=a):
                self.assertIsNone(cards.build_for_pick(pick))
                renderer.assert_not_called()
            with patch.object(cards,"team_logo",side_effect=[a,b]):
                self.assertEqual(cards.build_for_pick(pick),b"QA_ONLY")
                renderer.assert_called_once()


if __name__=="__main__":
    unittest.main(verbosity=2)
