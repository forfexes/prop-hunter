"""Offline test: approved PROP HUNTER single has a frame-free player layer.

A synthetic solid-color clean plate is used only for unit testing. It is NOT
published as a real design or a real tip, and never sent to Telegram.
"""
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from PIL import Image, ImageDraw
import prop_hunter_original_compositor as poster

portrait = Image.new("RGBA", (150, 240), (0, 0, 0, 0))
d = ImageDraw.Draw(portrait)
d.ellipse((18, 3, 133, 132), fill=(225, 174, 133, 255))
d.rounded_rectangle((0, 120, 149, 239), 22, fill=(38, 70, 160, 255))

# Pixel-level: alpha-cutout blends directly into background. No rectangle.
canvas = Image.new("RGBA", (691, 758), (11, 22, 39, 255))
assert poster._background_portrait(canvas, portrait, (0, 131, 246, 457))
assert canvas.getpixel((300, 290)) == (11, 22, 39, 255)
assert canvas.getpixel((245, 300)) == (11, 22, 39, 255)
assert canvas.getpixel((100, 365)) != (11, 22, 39, 255)
assert canvas.getpixel((100, 467)) == (11, 22, 39, 255), "Player overpainted the L5/L10/L15 header"
assert not poster._background_portrait(canvas, Image.new("RGB", (90, 180), "red"), (0, 131, 246, 457))
assert not poster._background_portrait(canvas, None, (0, 131, 246, 457))

with TemporaryDirectory() as folder:
    path = Path(folder) / "single.png"
    Image.new("RGBA", (691, 758), (11, 22, 39, 255)).save(path)
    with patch.object(poster, "APPROVED_MASTER", Path(folder)):
        poster._source.cache_clear()
        assert poster._source("single").size == (691, 758)
        team_logo = Image.new("RGBA", (80, 80), (0, 0, 0, 0))
        ImageDraw.Draw(team_logo).ellipse((8, 8, 72, 72), fill=(26, 122, 219, 255))
        teams = [("QA HOME", team_logo), ("QA AWAY", team_logo)]
        row = [{"name": "TEST ATHLETE", "photo": portrait,
                "label": "Test market (NOT A REAL TIP)", "odds": "@2.00",
                "form": "L5 3/5 L10 6/10 L15 9/15",
                "model": {"prob": "", "edge": "", "confidence": ""}}]
        with patch.object(poster, "_portrait", side_effect=AssertionError("Framed player must not render")), \
             patch.object(poster, "_clean_hero", side_effect=AssertionError("No legacy photo patch")), \
             patch.object(poster, "_hide_baked_single_head", side_effect=AssertionError("No baked athlete")), \
             patch.object(poster, "_rect", side_effect=AssertionError("No opaque runtime rectangle over a cleaned original")), \
             patch.object(poster, "_blend_fill", side_effect=AssertionError("No sample-text blending over a cleaned original")):
            data = poster.original_card("single", "SINGLE", "Test fixture",
                         "NBA", teams, row, "Einsatz 1u", "OFFEN")
        im = Image.open(BytesIO(data))
        assert im.size[0] == 1080
        assert im.getbbox()
        # An opaque photo cannot be displayed borderless: reject it.
        row[0]["photo"] = Image.new("RGB", (150, 240), "red")
        try:
            poster.original_card("single", "SINGLE", "Test fixture",
                                 "NBA", teams, row, "Einsatz 1u", "OFFEN")
        except ValueError as exc:
            assert "transparent player cutout" in str(exc)
        else:
            raise AssertionError("Opaque player picture was accepted")
    poster._source.cache_clear()

# The test uses an isolated temporary clean plate and never changes the
# actual approved or original user assets. Production remains separately gated.
print("BORDERLESS SINGLE: ALPHA CUTOUT, NO FRAME, CLEAN PLATE ONLY, OPAQUE REJECTED – PASS")
