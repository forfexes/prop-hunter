"""No-net artwork regression: one authentic crest per original slot.

The owner-supplied background, logo, gold frame and VS stay untouched; only
actual emblems are scaled from their visible alpha, without extra fake discs.
"""
import unittest

from PIL import Image, ImageDraw
from prop_hunter_owner_clean_single import (
    _fit_authentic_crest, _place_authentic_crest, _floating_team,
)
from prop_hunter_owner_clean_builder import _team as builder_team
from prop_hunter_owner_supplied_single import _logo as user_single_logo


def padded_logo():
    logo = Image.new("RGBA", (144, 128), (0, 0, 0, 0))
    ImageDraw.Draw(logo).rectangle(
        (55, 12, 85, 100), fill=(246, 32, 45, 255))
    return logo


def red_bounds(im):
    # The dynamic team names and static backgrounds are not crimson.
    mask = Image.new("L", im.size, 0)
    src, dst = im.convert("RGB").load(), mask.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b = src[x, y]
            if r >= 230 and g < 65 and b < 85:
                dst[x, y] = 255
    return mask.getbbox()


class TeamCrestGeometry(unittest.TestCase):
    def test_small_real_crest_fills_ring_instead_of_floating_as_sticker(self):
        emblem = Image.new("RGBA", (140, 140), (0, 0, 0, 0))
        ImageDraw.Draw(emblem).rectangle((55, 55, 84, 84),
                                         fill=(246, 32, 45, 255))
        fitted = _fit_authentic_crest(emblem, 71)
        self.assertEqual(fitted.size, (71, 71))
        canvas = Image.new("RGBA", (180, 180), (4, 12, 25, 255))
        original_corner = canvas.getpixel((0, 0))
        _place_authentic_crest(canvas, emblem, 90, 90, 71)
        self.assertEqual(canvas.getpixel((0, 0)), original_corner)
        self.assertEqual(red_bounds(canvas), (54, 54, 125, 125))
        # A miniature provider file must fail, not become a blurry pasted-on
        # badge or leave a mostly empty owner ring.
        with self.assertRaises(ValueError):
            _fit_authentic_crest(
                Image.new("RGBA", (12, 12), (246, 32, 45, 255)), 71)

    def test_opaque_badge_tile_never_pastes_a_sticker_on_any_owner_card(self):
        # Shared Single/Ladder/Builder and newest 512px Single use this helper.
        for mode in ("RGB", "RGBA"):
            with self.subTest(mode=mode):
                opaque=Image.new(mode,(90,90),
                                 (247,247,247) if mode=="RGB" else (247,247,247,255))
                ImageDraw.Draw(opaque).ellipse((8,8,81,81),
                                               fill=(32,145,220))
                with self.assertRaisesRegex(ValueError,"Opaque crest sticker"):
                    _fit_authentic_crest(opaque,71)
                clean=Image.new("RGBA",(512,512),(4,12,25,255))
                original=clean.copy()
                with self.assertRaisesRegex(ValueError,"Opaque crest sticker"):
                    user_single_logo(clean,("QA VERIFIED CLUB",opaque),191)
                from PIL import ImageChops
                self.assertIsNone(ImageChops.difference(clean,original).getbbox())

    def test_trim_transparency_preserves_shape_and_no_fake_sticker(self):
        icon = _fit_authentic_crest(padded_logo(), 54)
        self.assertLessEqual(max(icon.size), 54)
        self.assertGreater(icon.height, icon.width)
        self.assertEqual(icon.getchannel("A").getextrema(), (255, 255))
        for source in (Image.new("RGBA", (40, 40), (0, 0, 0, 0)),
                       Image.new("RGBA", (40, 40), (40, 30, 20, 0))):
            with self.assertRaises(ValueError):
                _fit_authentic_crest(source, 54)

    def test_single_ladder_shared_slots_center_both_axes(self):
        for cx, cy, diameter in ((273, 186, 71), (181, 186, 71),
                                 (213, 442, 52), (191, 108, 54)):
            with self.subTest(center=(cx, cy)):
                canvas = Image.new("RGBA", (691, 800), (4, 12, 25, 255))
                before = canvas.getpixel((0, 0))
                _place_authentic_crest(canvas, padded_logo(), cx, cy, diameter)
                bbox = red_bounds(canvas)
                self.assertIsNotNone(bbox)
                x0, y0, x1, y1 = bbox
                self.assertLessEqual(abs((x0+x1)/2 - cx), 1)
                self.assertLessEqual(abs((y0+y1)/2 - cy), 1)
                self.assertEqual(canvas.getpixel((0, 0)), before)
                self.assertLessEqual(x1-x0, diameter)
                self.assertLessEqual(y1-y0, diameter)

    def test_new_owner_single_crest_fills_the_actual_gold_circle(self):
        # The 512px owner's team ring is approximately 76px across.
        # A 54px badge looked like a loose sticker surrounded by black.
        im=Image.new("RGBA",(512,512),(4,12,25,255))
        emblem=Image.new("RGBA",(160,160),(0,0,0,0))
        ImageDraw.Draw(emblem).rectangle((18,18,142,142),
                                        fill=(246,32,45,255))
        user_single_logo(im,("QA NBA TEAM",emblem),191)
        x0,y0,x1,y1=red_bounds(im)
        self.assertGreaterEqual(x1-x0,68)
        self.assertLessEqual(x1-x0,70)
        self.assertLessEqual(abs((x0+x1)/2-191),1)
        self.assertLessEqual(abs((y0+y1)/2-108),1)

    def test_all_original_family_placers_use_one_identical_rule(self):
        logo = padded_logo()
        for callback, size, expected in (
            (lambda im: _floating_team(im, ("REAL TEAM", logo), 273),
             (691, 800), (273, 186)),
            (lambda im: builder_team(im, ("REAL TEAM", logo), 213),
             (691, 800), (213, 442)),
            (lambda im: user_single_logo(im, ("REAL TEAM", logo), 191),
             (512, 512), (191, 108)),
        ):
            with self.subTest(expected=expected):
                im = Image.new("RGBA", size, (4, 12, 25, 255))
                callback(im)
                x0, y0, x1, y1 = red_bounds(im)
                self.assertLessEqual(abs((x0+x1)/2 - expected[0]), 1)
                self.assertLessEqual(abs((y0+y1)/2 - expected[1]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
