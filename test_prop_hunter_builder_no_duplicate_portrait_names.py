"""Source-original NBA Builder: no player names under portrait cutouts.

Each athlete and market is printed exactly once in the numbered bet row.
The real background/logo and verified form may remain under the photos.
"""
import io
import unittest
from unittest.mock import patch
from PIL import Image, ImageDraw
import prop_hunter_owner_clean_builder as builder


def logo():
    im=Image.new("RGBA",(60,60),(0,0,0,0))
    ImageDraw.Draw(im).ellipse((2,2,58,58),fill=(30,133,211,255))
    return im


class PortraitDuplicatesQA(unittest.TestCase):
    def test_no_name_or_market_below_photo_for_all_builder_sizes(self):
        for n in (2,3,4,5,6,7):
            with self.subTest(legs=n):
                source=Image.new("RGBA",(691,867),(2,15,29,255))
                legs=[
                    {"name":f"PLAYER {i}", "label":f"Over {17+i}.5 points",
                     "odds":"@1.87", "photo":logo(),
                     "form":"L5 4/5 L10 7/10 L15 9/15"}
                    for i in range(1,n+1)
                ]
                texts=[]
                original=builder._text
                def record(draw,xy,text,**kwargs):
                    texts.append((xy,str(text)))
                    return original(draw,xy,text,**kwargs)
                with patch("prop_hunter_original_compositor._background_portrait",
                           return_value=True), patch.object(
                               builder,"_text",side_effect=record):
                    png=builder.render(
                        source,subtitle="QA · Fr 20.11.2026 · 20:00",
                        teams=[("HOME TEST",logo()),("AWAY TEST",logo())],
                        rows=legs,footer="Quote @3.45 · Einsatz 1u",
                        settlement="OFFEN")
                with Image.open(io.BytesIO(png)) as image:
                    self.assertEqual(image.width,1080)
                for item in legs:
                    for field in ("name","label"):
                        matches=[xy for xy,v in texts if v==item[field]]
                        self.assertEqual(len(matches),1,(n,item[field],matches))
                        self.assertGreaterEqual(matches[0][1],531)
                self.assertTrue(any("L15 9/15" in v for _,v in texts))


if __name__=="__main__":
    unittest.main(verbosity=2)
