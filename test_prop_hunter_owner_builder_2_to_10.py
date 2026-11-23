"""Exhaustive 2-10 original-owner NBA Builder geometry hardtest, offline only.

Uses a real approved *empty* original-derived stadium plate, with synthetic
transparent test cutouts. No player lookup, odds API, Telegram or Supabase.
"""
from __future__ import annotations

from io import BytesIO
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from PIL import Image, ImageChops, ImageDraw
import prop_hunter_owner_clean_builder as builder
from prop_hunter_original_compositor import _source

ROOT=Path(__file__).resolve().parent
SUBTITLE="BOSTON CELTICS vs NEW YORK KNICKS · Mo 23.11.2026 · 20:00"


def cutout(seed=0):
    im=Image.new("RGBA",(170,215),(0,0,0,0))
    d=ImageDraw.Draw(im)
    d.ellipse((22,6,148,151),fill=(95+seed*7,130,193,255))
    d.rounded_rectangle((12,136,162,208),radius=15,fill=(31,96+seed*8,162,255))
    return im


def badge(seed=0):
    im=Image.new("RGBA",(86,86),(0,0,0,0))
    d=ImageDraw.Draw(im)
    d.polygon(((43,3),(76,26),(63,75),(24,80),(7,24)),
              fill=(214,75+seed*14,42,255))
    return im


def rows(count):
    return [{"name":f"QA ATHLETE {i+1:02d}","label":f"Over {i+11}.5 points",
             "odds":f"@{1.65+i*.02:.2f}","photo":cutout(i),
             "form":"L5 4/5 L10 7/10 L15 10/15","result":""}
            for i in range(count)]


class AllOwnerBuilderLegCounts(unittest.TestCase):
    def setUp(self):
        self.teams=[("BOSTON CELTICS",badge(1)),("NEW YORK KNICKS",badge(2))]
        self.plate=_source("builder")
        self.assertEqual(self.plate.size,(691,867))

    def test_all_nine_counts_have_full_name_market_price_and_form(self):
        for count in range(2,11):
            with self.subTest(count=count):
                shown=[]
                original=builder._text
                def capture(draw,xy,value,**kwargs):
                    shown.append((str(value),xy))
                    return original(draw,xy,value,**kwargs)
                with patch.object(builder,"_text",side_effect=capture):
                    result=builder.render(
                        self.plate,subtitle=SUBTITLE,teams=self.teams,
                        rows=rows(count),footer="Quote @15.42 · Einsatz 1u",
                        settlement="OFFEN")
                extra_portrait=190 if count>7 else 0
                extra_ticket=max(0,count*32-177+12) if count>7 else 0
                height=round(1080*(867+extra_portrait+extra_ticket)/691)
                with Image.open(BytesIO(result)) as img:
                    self.assertEqual(img.format,"PNG")
                    self.assertEqual(img.size,(1080,height))
                    img.verify()
                for item in rows(count):
                    for field in ("name","label","odds"):
                        found=[y for text,(x,y) in shown if text==item[field]]
                        self.assertEqual(len(found),1,(count,field,item[field],found))
                self.assertEqual(sum(
                    text=="L5 4/5 · L10 7/10 · L15 10/15"
                    for text,_ in shown),count)
                status=[text for text,_ in shown if text.startswith("AUSWERTUNG:")]
                self.assertEqual(status,["AUSWERTUNG: OFFEN"])
                self.assertIn(f"{count}-LEG BUILDER",[t for t,_ in shown])
                outdir=os.getenv("PROP_OWNER_BUILDER_2_TO_10_QA")
                if outdir:
                    p=Path(outdir)
                    p.mkdir(parents=True,exist_ok=True)
                    (p/f"nba_owner_builder_{count}_LEGS_SANDBOX.png").write_bytes(result)

    def test_long_extension_preserves_original_header_while_adding_empty_rows(self):
        clean=self.plate.convert("RGB")
        for count in (8,9,10):
            with self.subTest(count=count):
                pic=builder.render(
                    self.plate,subtitle=SUBTITLE,teams=self.teams,
                    rows=rows(count),footer="Quote @15.42 · Einsatz 1u",
                    settlement="OFFEN")
                with Image.open(BytesIO(pic)) as im:
                    r=im.convert("RGB")
                    # Compare in the *same pixel scale* as the final output;
                    # round-trip resizing otherwise introduces test artifacts.
                    expected=clean.resize(
                        (1080,round(1080*867/691)),Image.Resampling.LANCZOS)
                    a=expected.crop((0,0,1080,108))
                    b=r.crop((0,0,1080,108))
                    self.assertIsNone(ImageChops.difference(a,b).getbbox())
        self.assertEqual(self.plate.size,(691,867))

    def test_invalid_counts_and_unverifiable_selection_fail_closed(self):
        for n in (1,11):
            with self.subTest(n=n),self.assertRaises(ValueError):
                builder.render(self.plate,subtitle=SUBTITLE,teams=self.teams,
                               rows=rows(n),footer="Quote @15.42",settlement="OFFEN")
        data=rows(10)
        data[9]["photo"]=None
        with self.assertRaisesRegex(ValueError,"genuine player"):
            builder.render(self.plate,subtitle=SUBTITLE,teams=self.teams,
                           rows=data,footer="Quote @15.42",settlement="OFFEN")
        with self.assertRaisesRegex(ValueError,"Calculated Builder quote"):
            builder.render(self.plate,subtitle=SUBTITLE,teams=self.teams,
                           rows=rows(10),footer="Berechnet 15.42",
                           settlement="OFFEN")


if __name__=="__main__":
    unittest.main(verbosity=2)
