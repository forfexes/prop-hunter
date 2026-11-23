"""Every NBA Ladder threshold owns its own observed L5/L10/L15 values.

No Telegram calls, no estimated model stats and no other player's form.
"""
import io
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

import prop_hunter_owner_clean_ladder as ladder


def badge():
    im = Image.new("RGBA", (65, 65), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse((2, 2, 62, 62), fill=(50, 145, 225))
    return im


class PerRungFormQA(unittest.TestCase):
    def run_card(self, n):
        plate = Image.new("RGBA", (691, 865), (5, 21, 40, 255))
        forms = [
            "L5 1/5 L10 3/10 L15 5/15",
            "L5 2/5 L10 5/10 L15 8/15",
            "L5 3/5 L10 6/10 L15 9/15",
            "L5 4/5 L10 7/10 L15 10/15",
            "L5 5/5 L10 8/10 L15 11/15",
            None,
        ]
        rows = [
            {"name": "TEST ATHLETE", "label": f"Under {12 - i}.5 points",
             "photo": None, "odds": f"@{1.5+i/10:.2f}",
             "form": forms[i], "result": "OFFEN"}
            for i in range(n)
        ]
        seen = []
        original = ladder._text
        def witness(draw, pos, value, **kwargs):
            seen.append((pos, str(value), kwargs))
            return original(draw, pos, value, **kwargs)
        with patch("prop_hunter_original_compositor._background_portrait",
                   return_value=True), patch.object(ladder, "_text",
                                                    side_effect=witness):
            raw = ladder.render(plate, subtitle="QA · Fr 20.11.2026 · 20:00",
                       teams=[("HOME TEST", badge()), ("AWAY TEST", badge())],
                       rows=rows, footer="Einsatz 1u", settlement="OFFEN")
        with Image.open(io.BytesIO(raw)) as img:
            self.assertEqual(img.width,1080)
        return seen

    def test_different_thresholds_different_visible_l5_l10_l15(self):
        seen = self.run_card(4)
        per_rung = [(xy, text) for xy, text, kw in seen
                    if xy[0] == 378 and "L5" in text]
        self.assertEqual(len(per_rung),4)
        self.assertEqual([text for _, text in per_rung],[
            ladder._observed_form_windows(
                f"L5 {i}/5 L10 {i+2}/10 L15 {i+4}/15")
            for i in range(1,5)
        ])
        self.assertEqual(len(set(text for _, text in per_rung)),4)
        self.assertNotIn((374, 681), [xy for xy, _, _ in per_rung])

    def test_six_rungs_keep_unknown_values_unknown(self):
        seen = self.run_card(6)
        value_lines = [(xy, text, kw) for xy, text, kw in seen
                       if xy[0]==378 and "L5" in text]
        self.assertEqual(len(value_lines),6)
        self.assertEqual(value_lines[-1][1], "L5 — · L10 — · L15 —")
        self.assertEqual(len({xy[1] for xy,_,_ in value_lines}),6)
        for xy,_,kw in value_lines:
            self.assertEqual(kw["max_width"],235)
            self.assertEqual(kw["size"],12)
        results = [(xy,text) for xy,text,_ in seen if xy[0]==562]
        self.assertEqual(len(results),6)
        self.assertTrue(all(text=="OFFEN" for _,text in results))


if __name__=="__main__":
    unittest.main(verbosity=2)
