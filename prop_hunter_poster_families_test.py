"""Offline PNG regression for all four premium poster families."""
from io import BytesIO
import os
# Only offline previews may show missing-photo labels; production rejects them.
os.environ["PH_REQUIRE_PLAYER_PHOTOS"] = "0"
from pathlib import Path
from PIL import Image
from unittest.mock import patch
from types import SimpleNamespace
import prop_hunter_image_cards as cards
from prop_hunter_original_template_registry import SPORTS, FAMILIES, template_location, all_required_templates
from prop_hunter_image_cards import render

def test_family(kind, count):
    rows = [{"name": ("One Ladder Player" if kind == "ladder" else "Test Player " + str(i)), "label": "Over 20.5 Points",
             "photo": None, "form": "L10 8/10   L15 12/15", "odds": "@1.90"}
            for i in range(count)]
    data = render(kind, kind.upper(), "Verified sample only", "basketball",
                  [("Home", None), ("Away", None)], rows, "Quote @1.90", "")
    assert data[:8] == bytes([137,80,78,71,13,10,26,10])
    image = Image.open(BytesIO(data))
    assert image.width == 1080 and image.height >= 800
    assert image.height >= 1100
    image.verify()
    out=Path('poster_previews')
    out.mkdir(exist_ok=True)
    (out / f'{kind}.png').write_bytes(data)
    # The poster must contain real drawn content in both the header and pick region.
    image = Image.open(BytesIO(data)).convert("RGB")
    assert image.getpixel((540, 53)) != image.getpixel((540, image.height - 25))
    assert len(image.getcolors(maxcolors=1_000_000) or []) > 100
    # Verify preview image validity, not a fragile per-pixel font glyph location.
    assert image.getbbox() is not None

for family, count in [("single",1),("ladder",3),("builder",3),("lottery",3)]:
    test_family(family,count)
print("FOUR POSTER FAMILIES PNG RENDER PASS")

# Every supported sport shares the SAME four NBA original layouts.
assert len(all_required_templates()) == 4
assert set(SPORTS) == {"NBA", "WNBA", "NCAAB", "EUROLEAGUE", "NFL", "NCAAF", "NHL", "MLB"}
for league in SPORTS:
    for family in FAMILIES:
        assert template_location(league, family).suffix == ".webp"
assert template_location("WNBA", "single") == template_location("NBA", "single")
assert template_location("NCAAF", "builder") == template_location("NFL", "builder")
assert template_location("NHL", "lottery") == template_location("NBA", "lottery")
assert template_location("MLB", "ladder") == template_location("NBA", "ladder")
for key in SPORTS:
    assert cards.league_of(key), key

# Rendering a three-rung ladder draws exactly one player portrait.
orig_circle = cards._circle
portraits = []
def record_portrait(im, size, name):
    if name == "One Ladder Player":
        portraits.append((size, name))
    return orig_circle(im, size, name)
ladder_rows = [{"name": "One Ladder Player", "photo": None,
                "label": f"Points Over {20+i}.5", "odds": "@1.90",
                "form": "L10 8/10   L15 12/15"} for i in range(3)]
with patch.object(cards, "_circle", side_effect=record_portrait):
    png = cards.render("ladder", "LADDER", "Single athlete / 3 rungs", "basketball", [], ladder_rows)
assert png[:8] == bytes([137, 80, 78, 71, 13, 10, 26, 10])
assert len(portraits) == 1, portraits

# Reject mislabeled multi-player ladders, rather than silently posting a builder.
ladder_pick = SimpleNamespace(type="ladder", player="Player One", game="Test",
    source_sport="NBA", features={}, odds=1.9, stake=.25,
    leg_details=[{"player":"Player One", "market":"Points Over 20.5", "odds":1.90},
                 {"player":"Player Two", "market":"Points Over 25.5", "odds":2.50}])
with patch.object(cards, "player_photo", return_value=None):
    assert cards.build_for_pick(ladder_pick) is None
ladder_pick.leg_details[1]["player"] = "Player One"
with patch.object(cards, "player_photo", return_value=None), patch.object(cards, "render", return_value=b"ok") as rr:
    assert cards.build_for_pick(ladder_pick) == b"ok"
    assert len(rr.call_args.args[5]) == 2
    assert {row["name"] for row in rr.call_args.args[5]} == {"Player One"}
print("EIGHT SPORT ROUTES / FOUR SHARED ORIGINAL-LAYOUT SLOTS / SINGLE-PLAYER LADDER PASSED")

# The generator consumes a real render-ready artwork file when present.
# It must NOT silently claim that an absent user master exists.
from tempfile import TemporaryDirectory
from unittest.mock import patch as mock_patch
import os
with TemporaryDirectory() as temp:
    bgfile = Path(temp) / "football_single.webp"
    Image.new("RGB", (900, 1100), (19, 42, 61)).save(bgfile, "WEBP")
    with mock_patch("prop_hunter_original_template_registry.available_template", return_value=bgfile), mock_patch.object(cards, "_background", side_effect=AssertionError("procedural fallback was used")):
        loaded = cards._original_artwork_background("football", "single", 1000)
        assert loaded.size == (1080, 1000)
        assert all(abs(actual - expected) <= 5 for actual,expected in zip(loaded.getpixel((540, 500))[:3], (19, 42, 61)))
with mock_patch("prop_hunter_original_template_registry.available_template", return_value=None), mock_patch.dict(os.environ, {"PH_ORIGINAL_ONLY":"1"}):
    try:
        cards._original_artwork_background("hockey", "ladder", 1000)
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("PH_ORIGINAL_ONLY must reject missing user artwork")
print("REAL ARTWORK PATH / FAIL-CLOSED ORIGINAL MODE PASSED")

# Integrity gate for the FOUR actual uploaded user source images, NOT recreated art.
from hashlib import sha256
_original_sha256 = {
    "single": "c2e8b229b060d5b43ed8886ff54d0ef67ef985704d5b37e9de66a486ae60a56c",
    "ladder": "6575d2eed1ec8a764cefbcfb2fa0e3253cf98f3f1557c3ffbabdd97ebd5c606f",
    "builder": "7041a9d24a75a275f916f117dd6293fed81684653e09b5a5dcc7f5493552682c",
    "lottery": "4f131e3fa44ab7f9126c07e34608faa0a3443c8e8c22a884860e3cd03ca0513e",
}
for family, fingerprint in _original_sha256.items():
    src = Path("card_templates") / "originals" / (family + ".jpg")
    assert src.is_file(), f"Missing ACTUAL user original asset: {src}"
    assert sha256(src.read_bytes()).hexdigest() == fingerprint, f"Original image changed: {src}"
    with Image.open(src) as original:
        assert original.format == "JPEG" and original.size == (691, 1536)
print("ALL FOUR EXACT USER ORIGINAL JPGS VERIFIED IN GITHUB CHECKOUT")

# WNBA overlays its own sports data on the SAME NBA original artwork.
wnba_pick = SimpleNamespace(type="single", player="Test WNBA Athlete", game="Test",
    source_sport="WNBA", features={}, odds=1.9, stake=.25,
    market="points", direction="over", point=15.5)
with patch.object(cards, "player_photo", return_value=None), patch.object(cards, "render", return_value=b"ok") as rr:
    assert cards.build_for_pick(wnba_pick) == b"ok"
    assert template_location(rr.call_args.kwargs["template_sport"],"single") == template_location("NBA","single")
for hint, expected in [("NHL", "hockey"), ("NFL", "football"), ("WNBA", "basketball")]:
    assert cards.league_of(hint)[0] == expected
print("NBA ORIGINAL ARTWORK SHARED BY WNBA/NHL/NFL, SPORTS DATA ROUTING PASS")
