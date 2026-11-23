"""Original NBA Builder/Lottery: actual L5/L10/L15 for EACH priced leg.

Sandbox synthetic fixtures, no bookmaker API, Telegram or live sends.
Never infer a missing hit count or borrow another athlete's form.
"""
from __future__ import annotations

import io
import unittest
from unittest.mock import patch
from PIL import Image, ImageDraw

import prop_hunter_owner_clean_builder as builder
import prop_hunter_owner_clean_lottery as lottery
from prop_hunter_original_compositor import _source

TEST_FORM = ("L5 3/5 L10 7/10 L15 12/15", "L10 4/10", "L5 0/0 L15 15/15")
EXPECTED = (
    "L5 3/5 · L10 7/10 · L15 12/15",
    "L5 — · L10 4/10 · L15 —",
    "L5 — · L10 — · L15 15/15",
)


def qa_photo():
    im=Image.new("RGBA",(128,200),(0,0,0,0))
    ImageDraw.Draw(im).ellipse((18,18,106,180),fill=(22,117,177,255))
    return im


def qa_logo():
    im=Image.new("RGBA",(72,72),(0,0,0,0))
    ImageDraw.Draw(im).rectangle((22,6,50,66),fill=(247,196,75,255))
    return im


class PerLegL5L10L15QA(unittest.TestCase):
    def test_builder_helper_never_invents_missing_samples(self):
        for input_form, expected in zip(TEST_FORM,EXPECTED):
            with self.subTest(input_form=input_form):
                self.assertEqual(builder._form_label(input_form,True),expected)
        self.assertEqual(builder._form_label("",True),"L5 — · L10 — · L15 —")
        self.assertEqual(builder._form_label("L15 0/0",True),
                         "L5 — · L10 — · L15 —")

    def _capture(self, renderer, *args, **kwargs):
        rows=[]
        real=renderer._text
        def track(draw, position, value, **options):
            rows.append(str(value))
            return real(draw,position,value,**options)
        with patch.object(renderer,"_text",side_effect=track), patch(
                "prop_hunter_original_compositor._background_portrait",
                return_value=True):
            image=renderer.render(*args,**kwargs)
        with Image.open(io.BytesIO(image)) as im:
            im.verify()
        return rows

    def test_builder_each_individual_player_shows_own_observed_windows(self):
        rows=[{"name":f"QA ATHLETE {i+1}","label":"QA LINE",
               "odds":"@—","photo":qa_photo(),"form":form,"result":""}
              for i,form in enumerate(TEST_FORM)]
        teams=[("QA HOME",qa_logo()),("QA AWAY",qa_logo())]
        printed=self._capture(builder,_source("builder"),
                 subtitle="QA HOME vs QA AWAY · Mo 23.11.2026 · 20:00",
                 teams=teams,rows=rows,footer="Einsatz 1u",
                 settlement="OFFEN")
        self.assertEqual([label for label in printed if label.startswith("L5 ")],
                         list(EXPECTED))

    def test_lottery_each_fixture_has_independent_windows_not_other_player(self):
        rows=[{"name":f"QA ATHLETE {i+1}","label":"QA LINE",
               "odds":"@—","photo":qa_photo(),"form":form,
               "game":f"QA HOME vs QA AWAY {20+i:02d}:30",
               "result":""}
              for i,form in enumerate(TEST_FORM)]
        # This is a purpose-labelled MOCK ticket for offline geometry only;
        # the production pipeline independently requires a verified bookie.
        printed=self._capture(lottery,_source("lottery"),rows=rows,
                  footer="Quote @2.00 · Einsatz 1u",settlement="OFFEN")
        self.assertEqual([label for label in printed if label.startswith("L5 ")],
                         list(EXPECTED))


if __name__=="__main__":
    unittest.main(verbosity=2)
