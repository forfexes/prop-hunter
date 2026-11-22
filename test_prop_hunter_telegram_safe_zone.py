"""Offline regression: Telegram metadata must never hide owner's real artwork.

No Telegram credentials, photos, fixtures or betting data are needed.
"""
import io
import os
from types import SimpleNamespace as N
from PIL import Image, ImageDraw, ImageChops

from prop_hunter_telegram_safe_zone import append_owner_margin, margin_height, split_owner_margin
from prop_hunter_owner_pixel_qa import APPROVED, owner_pixel_provenance


def encode(im):
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


for body_height in (1183, 1352, 1540, 1700):
    source = Image.new("RGB", (1080, body_height), (2, 15, 42))
    ImageDraw.Draw(source).rectangle(
        (850, body_height - 80, 1079, body_height - 10),
        fill=(50, 130, 230),
    )
    original = encode(source)
    extended = append_owner_margin(original)
    with Image.open(io.BytesIO(extended)) as result:
        assert result.size == (1080, body_height + margin_height(body_height))
        pristine, padded = split_owner_margin(result, (body_height,))
        assert padded is True
        assert ImageChops.difference(source, pristine).getbbox() is None
        # No copied handle, text, time, odds or rectangle in the blank tail.
        last_row = result.crop((0, body_height - 1, 1080, body_height))
        for y in (body_height, result.height - 1):
            assert ImageChops.difference(
                last_row, result.crop((0, y, 1080, y + 1))
            ).getbbox() is None
        vandal = result.copy()
        ImageDraw.Draw(vandal).text(
            (1010, result.height - 40), "@OLD", fill=(255, 255, 255)
        )
        try:
            split_owner_margin(vandal, (body_height,))
        except ValueError:
            pass
        else:
            raise AssertionError("Nonempty/overpainted Telegram margin was accepted")
    print("SAFE_ZONE_EXACT_ORIGINAL", body_height)

for fake in (b"not a PNG", b"", b"\x89PNG\r\n\x1a\ntruncated"):
    try:
        append_owner_margin(fake)
    except (ValueError, OSError):
        pass
    else:
        raise AssertionError("Invalid owner media accepted")

samples = {
    "single": N(type="single"),
    "ladder": N(type="ladder"),
    "builder": N(type="betbuilder", features={}),
    "lottery": N(type="lottery"),
}
os.environ["PH_REQUIRE_TELEGRAM_SAFE_MARGIN"] = "1"
for family, pick in samples.items():
    with Image.open(APPROVED / (family + ".png")) as art:
        clean = art.convert("RGB")
        body = clean.resize(
            (1080, round(1080 * clean.height / clean.width)),
            Image.Resampling.LANCZOS,
        )
    raw = encode(body)
    allowed, reason = owner_pixel_provenance(pick, append_owner_margin(raw))
    assert allowed, (family, reason)
    assert owner_pixel_provenance(pick, raw) == (
        False, "owner_telegram_margin_missing"
    )
    print("OWNER_PUBLISH_REQUIRES_SAFE_ZONE", family)

# Six-stage, same-player ladder has a separately approved 120-px empty band.
with Image.open(APPROVED / "ladder.png") as src:
    clean = src.convert("RGB")
    tall = Image.new("RGB", (691, 985), (3, 15, 29))
    tall.paste(clean.crop((0, 0, 691, 730)), (0, 0))
    tall.paste(clean.crop((0, 515, 691, 635)), (0, 730))
    tall.paste(clean.crop((0, 730, 691, 865)), (0, 850))
    body = tall.resize((1080, round(1080 * 985 / 691)), Image.Resampling.LANCZOS)
    assert owner_pixel_provenance(
        N(type="betbuilder", features={"same_player_multistat": True}),
        append_owner_margin(encode(body)),
    ) == (True, "source_original_pixels_verified")
print("OWNER_TELEGRAM_SAFE_AREA_QA_PASSED")
