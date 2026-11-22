"""Preserve every pixel of an approved owner card in Telegram's chat preview.

Telegram draws message time/edit metadata over the bottom-right of photo
thumbnails. Append a metadata-only gutter UNDER the completed original card;
never resize, crop, repaint or move any of the owner's card pixels. The gutter
is a repeat of the last, text-free scanline of the finished stadium image.
This is independent of device-specific Telegram UI geometry.
"""
from __future__ import annotations

import io

from PIL import Image, ImageChops

PNG = b"\x89PNG\r\n\x1a\n"


def margin_height(body_height: int) -> int:
    if body_height < 400:
        raise ValueError("Owner card too short for Telegram-safe preview")
    return max(200, round(body_height * 0.16))


def append_owner_margin(png: bytes) -> bytes:
    """Protect the original footer with an entirely separate bottom image band."""
    if not isinstance(png, (bytes, bytearray)) or not png.startswith(PNG):
        raise ValueError("Owner Telegram card must be a real PNG")
    with Image.open(io.BytesIO(png)) as source:
        if source.format != "PNG" or source.width != 1080:
            raise ValueError("Owner Telegram card needs its full 1080px original")
        original = source.convert("RGB")
    width, height = original.size
    gap = margin_height(height)
    # Preserve the rendered owner image EXACTLY. Only the extra, empty area
    # is filled with actual floor pixels; no old text/odds are painted over.
    last_line = original.crop((0, height - 1, width, height))
    background = last_line.resize((width, gap), Image.Resampling.NEAREST)
    result = Image.new("RGB", (width, height + gap))
    result.paste(original, (0, 0))
    result.paste(background, (0, height))
    output = io.BytesIO()
    result.save(output, "PNG", optimize=True)
    return output.getvalue()


def split_owner_margin(img: Image.Image, body_heights: tuple[int, ...]):
    """Verify the metadata area contains no labels, artwork or substituted card.

    Returns (exact unmodified body, has_margin). Old, unpadded QA fixtures are
    still allowed outside production. Any forged or corrupt appended strip is
    rejected before Telegram publication.
    """
    source = img.convert("RGB")
    for height in body_heights:
        if source.height == height:
            return source, False
        if source.height != height + margin_height(height):
            continue
        gap = source.height - height
        repeated = source.crop((0, height - 1, source.width, height)).resize(
            (source.width, gap), Image.Resampling.NEAREST
        )
        actual = source.crop((0, height, source.width, source.height))
        if ImageChops.difference(repeated, actual).getbbox() is not None:
            raise ValueError("Telegram margin has nonempty or altered content")
        return source.crop((0, 0, source.width, height)), True
    raise ValueError("Telegram owner card has invalid full-height geometry")
