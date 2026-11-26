"""Offline QA: user-requested centred player name and larger transparent portrait.

No Telegram, no live odds, no overwritten owner master. Both 691px and
512px authentic source formats are rendered with synthetic QA input.
"""
from __future__ import annotations

from io import BytesIO
import os
from pathlib import Path
from unittest.mock import patch
import unittest

from PIL import Image, ImageDraw

import prop_hunter_owner_clean_single as clean
import prop_hunter_owner_supplied_single as supplied

ROOT = Path(__file__).resolve().parent
QA = {"PH_NBA_SINGLE_CENTERED_PREVIEW": "1"}
EXPECTED_691 = (345, 312)
EXPECTED_512 = (256, 199)


def sample_assets():
    logo = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    ImageDraw.Draw(logo).ellipse((10, 10, 89, 89), fill=(255, 65, 80, 255))
    second = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    ImageDraw.Draw(second).ellipse((10, 10, 89, 89), fill=(49, 141, 228, 255))
    portrait = Image.new("RGBA", (170, 215), (0, 0, 0, 0))
    ink = ImageDraw.Draw(portrait)
    ink.ellipse((40, 8, 131, 109), fill=(201, 151, 110, 255))
    ink.polygon([(25, 215), (30, 145), (53, 110), (113, 110),
                 (146, 152), (152, 215)], fill=(28, 113, 202, 255))
    return [("QA TEAM A", logo), ("QA TEAM B", second)], portrait


def sample_fields(name="QA TEST ATHLETE"):
    teams, portrait = sample_assets()
    return {
        "title": "SINGLE",
        "subtitle": "QA TEAM A vs QA TEAM B · Di 24.11.2026 · 20:00",
        "teams": teams,
        "row": {
            "name": name,
            "photo": portrait,
            "label": "Under 12.5 points",
            "odds": "@1.76",
            "form": "L5 4/5 · L10 9/10 · L15 13/15",
            "model": {"prob": "71.2%", "edge": "+14.3%", "confidence": "89/100"},
        },
        "footer": "Quote @1.76 · Einsatz 1u",
        "settlement": "OFFEN",
    }


class CenteredSingleQA(unittest.TestCase):
    def test_centered_and_original_right_column_691(self):
        fields = sample_fields()
        plate_path = ROOT / "card_templates" / "approved" / "single.png"
        original = Image.open(plate_path).convert("RGB")
        positions = []
        images = []
        original_text = clean._text
        original_portrait = __import__("prop_hunter_original_compositor")._background_portrait

        def observe_text(draw, position, value, **kw):
            positions.append((str(value), position))
            return original_text(draw, position, value, **kw)

        def observe_portrait(im, person, rect):
            images.append(rect)
            return original_portrait(im, person, rect)

        with patch.dict(os.environ, QA), patch.object(clean, "_text", side_effect=observe_text), \
                patch("prop_hunter_original_compositor._background_portrait",
                      side_effect=observe_portrait):
            raw = clean.render(original, **fields)
        self.assertIn((fields["row"]["name"], EXPECTED_691), positions)
        self.assertIn((0, 123, 264, 457), images)
        self.assertIn(("Di 24.11.2026", (597, 163)), positions)
        self.assertIn(("20:00 Uhr", (597, 202)), positions)
        with Image.open(BytesIO(raw)) as out:
            self.assertEqual(out.width, 1080)
            image = out.convert("RGB")
        expected = original.resize(image.size, Image.Resampling.LANCZOS)
        for x, y in ((9, 9), (619, 285), (625, 444), (620, 710)):
            sx = round(x * 1080 / 691)
            sy = round(y * 1080 / 691)
            self.assertEqual(image.getpixel((sx, sy)), expected.getpixel((sx, sy)))

    def test_base_691_coords_stay_unchanged_until_approval(self):
        fields = sample_fields()
        plate = Image.open(ROOT / "card_templates" / "approved" / "single.png").convert("RGB")
        positions = []
        orig = clean._text

        def observe(d, pos, val, **kw):
            positions.append((str(val), pos))
            return orig(d, pos, val, **kw)

        with patch.dict(os.environ, {"PH_NBA_SINGLE_CENTERED_PREVIEW": "0"}), \
                patch.object(clean, "_text", side_effect=observe):
            clean.render(plate, **fields)
        self.assertIn((fields["row"]["name"], (402, 312)), positions)

    def test_centered_source_exact_512_and_long_name(self):
        fields = sample_fields(name="Shai Gilgeous-Alexander")
        positions = []
        old_write = supplied._write

        def observe(draw, pos, val, *args, **kw):
            positions.append((str(val), pos))
            return old_write(draw, pos, val, *args, **kw)

        with patch.dict(os.environ, QA), patch.object(supplied, "_write", side_effect=observe):
            raw = supplied.render(**fields)
        self.assertIn((fields["row"]["name"], EXPECTED_512), positions)
        self.assertIn(("Di 24.11.2026", (459, 84)), positions)
        self.assertIn(("20:00 Uhr", (457, 115)), positions)
        with Image.open(BytesIO(raw)) as out:
            self.assertEqual(out.size, (1080, 1080))
        # Original source and exact static logo/graphics are never rewritten.
        before = supplied.SOURCE.read_bytes()
        self.assertEqual(__import__("hashlib").sha256(before).hexdigest(),
                         supplied.SOURCE_SHA256)

    def test_enlarged_cutout_no_silhouette_or_protected_masthead(self):
        _, portrait = sample_assets()
        basic = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
        bigger = basic.copy()
        supplied._portrait(basic, portrait, centered_qa=False)
        supplied._portrait(bigger, portrait, centered_qa=True)
        alpha1, alpha2 = basic.getchannel("A"), bigger.getchannel("A")
        self.assertGreater(sum(alpha2.histogram()[128:]), sum(alpha1.histogram()[128:]))
        bounds = alpha2.getbbox()
        self.assertIsNotNone(bounds)
        self.assertGreaterEqual(bounds[1], 70)
        self.assertLessEqual(bounds[2], 215)
        self.assertEqual(alpha2.getpixel((280, 120)), 0)
        # Missing photos never become synthetic face silhouettes.
        with self.assertRaises(ValueError):
            supplied._portrait(bigger, Image.new("RGBA", (200, 250), (0, 0, 0, 0)),
                               centered_qa=True)

    def test_unmodified_default_512_text_location(self):
        fields = sample_fields()
        hits = []
        original = supplied._write

        def see(d, pos, v, *a, **kw):
            hits.append((str(v), pos))
            return original(d, pos, v, *a, **kw)

        with patch.dict(os.environ, {"PH_NBA_SINGLE_CENTERED_PREVIEW": "0"}), \
                patch.object(supplied, "_write", side_effect=see):
            supplied.render(**fields)
        self.assertIn((fields["row"]["name"], (308, 199)), hits)

    def test_production_geometry_release_and_historical_pin(self):
        from types import SimpleNamespace
        from prop_hunter_nba_owner_bridge import centered_single_enabled
        from prop_hunter_image_publication_gate import owner_image_signature
        pick=SimpleNamespace(type="single")
        env={"PH_NBA_CENTERED_SINGLE_RELEASE":"1","PH_NBA_SINGLE_CENTERED_PREVIEW":"0"}
        with patch.dict(os.environ,env):
            self.assertTrue(centered_single_enabled(pick))
            self.assertFalse(centered_single_enabled({"_owner_single_centered_20261125":False}))
            self.assertTrue(centered_single_enabled({"_owner_single_centered_20261125":True}))
            original=owner_image_signature(pick)
            with patch.dict(os.environ,{"PH_NBA_CENTERED_SINGLE_RELEASE":"0"}):
                self.assertFalse(centered_single_enabled(pick))
                self.assertNotEqual(original,owner_image_signature(pick))

    def test_centered_qa_cannot_publish_without_owner_visual_approval(self):
        # The release guard must run BEFORE any assets, odds or Telegram
        # state can be accessed and must leave ordinary production unchanged.
        from prop_hunter_nba_owner_bridge import render_owner
        with patch.dict(os.environ, {
            "PH_NBA_SINGLE_CENTERED_PREVIEW": "1",
            "PH_NBA_CENTERED_SINGLE_VISUAL_APPROVED": "0",
        }):
            with self.assertRaisesRegex(
                    ValueError, "centered_single_requires_owner_visual_approval"):
                render_owner(None, "single_assists", [], [], {}, [])

    def test_preview_no_unknown_arena_and_preserves_result_on_original(self):
        f = sample_fields()
        with patch.dict(os.environ, QA):
            win = supplied.render(**dict(f, settlement="GEWONNEN"))
            open_card = supplied.render(**f)
        self.assertNotEqual(win, open_card)
        self.assertEqual(supplied._get_time(f["subtitle"]),
                         ("Di 24.11.2026", "20:00"))


def save_qa_previews(outdir):
    root = Path(outdir)
    root.mkdir(parents=True, exist_ok=True)
    f = sample_fields()
    for name in ("QA TEST ATHLETE", "Shai Gilgeous-Alexander"):
        x = sample_fields(name)
        safe = name.lower().replace(" ", "_").replace("-", "_")
        with patch.dict(os.environ, QA):
            with Image.open(ROOT / "card_templates" / "approved" / "single.png") as plate:
                (root / f"owner_691_{safe}_OFFLINE.png").write_bytes(
                    clean.render(plate.convert("RGB"), **x))
            (root / f"owner_512_{safe}_OFFLINE.png").write_bytes(supplied.render(**x))


if __name__ == "__main__":
    unittest.main()
