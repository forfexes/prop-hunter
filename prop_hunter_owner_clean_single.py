"""Render a PROP HUNTER Single on the owner's already cleaned bitmap.

No opaque cover-up of a screenshot or fallback poster. This module does not
publish to Telegram or authorize the use of an unfinished source plate.
"""
from __future__ import annotations

import io
import re

from PIL import Image, ImageDraw, ImageFont

DARK_GREEN = (4, 46, 34, 110)
DARK_GOLD = (70, 41, 5, 118)
GOLD = (255, 218, 101)
WHITE = (250, 251, 253)
GREEN = (63, 243, 155)
RED = (255, 88, 104)
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf"


def _font(size):
    try:
        return ImageFont.truetype(FONT, size)
    except OSError:
        return ImageFont.load_default()


def _text(draw, position, value, *, size=20, max_width=240,
          color=WHITE, anchor="mm"):
    value = str(value or "").strip()
    if not value:
        return
    font = _font(size)
    while size > 11 and draw.textlength(value, font=font) > max_width:
        size -= 1
        font = _font(size)
    if draw.textlength(value, font=font) > max_width:
        raise ValueError("Owner Single text too long for its actual source slot")
    draw.text(position, value, fill=color, font=font, anchor=anchor)


def _floating_team(im, team, cx):
    if (not team or not str(team[0] or "").strip()
            or not isinstance(team[1], Image.Image)):
        raise ValueError("Genuine team logo and club name are mandatory")
    name, logo = team
    icon = logo.convert("RGBA")
    icon.thumbnail((71, 71), Image.Resampling.LANCZOS)
    im.alpha_composite(icon, (int(cx - icon.width / 2), 151))
    _text(ImageDraw.Draw(im), (cx, 250), name, size=16, max_width=123)


def _observed_form(draw, raw):
    value = str(raw or "")
    for n, y in ((5, 522), (10, 552), (15, 584)):
        match = re.search(r"\bL" + str(n) + r"\s+(\d+)/(\d+)\b", value, re.I)
        hit = None
        if match:
            h, total = int(match.group(1)), int(match.group(2))
            if 0 <= h <= total <= n and total > 0:
                hit = f"{h}/{total}"
        _text(draw, (63, y), f"L{n}", size=18, max_width=50)
        _text(draw, (230, y), hit or "—", size=18, max_width=85,
              color=GREEN if hit else GOLD, anchor="rm")


def _models(draw, model):
    if not isinstance(model, dict):
        model = {}
    for j, (label, key) in enumerate(
            (("PROB", "prob"), ("EDGE", "edge"), ("CONF", "confidence"))):
        value = str(model.get(key) or "").strip()
        if value and key in ("prob", "edge") and not value.endswith("%"):
            value += "%"
        _text(draw, (305, 519 + 29 * j), label, size=16, max_width=65)
        _text(draw, (490, 519 + 29 * j), value or "—", size=16,
              max_width=115, color=GREEN if value else GOLD, anchor="rm")


def _verified_time(subtitle):
    # Only a supplied, timezone-aware and already validated fixture kickoff.
    # The owner bridge constructs this string from the actual commencement.
    matched = re.search(
        r"\b(?:Mo|Di|Mi|Do|Fr|Sa|So)\s+\d{2}\.\d{2}\.(?:\d{4})?\s*·\s*\d{2}:\d{2}",
        str(subtitle or ""),
    )
    if not matched:
        return "", ""
    left, _, right = matched.group(0).partition("·")
    return left.strip(), right.strip()


def render(plate: Image.Image, *, title: str, subtitle: str, teams: list,
           row: dict, footer: str, settlement: str) -> bytes:
    """Render from a data-free, approved plate, without old-screenshot masks."""
    if plate.size != (691, 758):
        raise ValueError("Single owner plate must match the exact original crop")
    if len(teams) != 2 or not isinstance(row, dict):
        raise ValueError("Single requires two real teams and one verified athlete")

    from prop_hunter_original_compositor import _background_portrait
    im = plate.convert("RGBA").copy()
    for center, team in zip((273, 457), teams):
        _floating_team(im, team, center)
    if not _background_portrait(im, row.get("photo"), (0, 129, 239, 457)):
        raise ValueError("Actual transparent athlete cutout required")

    date, clock = _verified_time(subtitle)
    d = ImageDraw.Draw(im)
    _text(d, (597, 163), date, size=17, max_width=176, color=GOLD)
    _text(d, (597, 202), clock + " Uhr" if clock else "",
          size=18, max_width=170)
    _text(d, (402, 312), row.get("name"), size=29, max_width=293)
    if title and title not in ("SINGLE",):
        _text(d, (402, 347), title, size=16, max_width=280, color=GOLD)

    # New translucent empty UI slots preserve the original stadium texture.
    # No dark, opaque rectangles are used to hide sample players or words.
    tint = Image.new("RGBA", im.size, (0, 0, 0, 0))
    p = ImageDraw.Draw(tint)
    p.rounded_rectangle((168, 382, 471, 439), radius=9,
                        fill=DARK_GREEN, outline=(47, 239, 151, 232), width=2)
    p.rounded_rectangle((473, 382, 621, 439), radius=9,
                        fill=DARK_GOLD, outline=(252, 205, 81, 232), width=2)
    im = Image.alpha_composite(im, tint)
    d = ImageDraw.Draw(im)
    _text(d, (319, 410), row.get("label"), size=28, max_width=277)
    _text(d, (547, 410), row.get("odds"), size=27,
          max_width=125, color=GOLD)
    _text(d, (159, 476), "LETZTE SPIELE", size=18, max_width=168)
    _observed_form(d, row.get("form"))
    _models(d, row.get("model"))
    amount = re.search(r"Einsatz\s+([\d.,]+u)", str(footer or ""), re.I)
    _text(d, (597, 553), amount.group(1) if amount else "—",
          size=24, max_width=115, color=GOLD)
    state = str(settlement or "OFFEN").strip()
    status_color = (GREEN if "gewonnen" in state.casefold()
                    else RED if "verloren" in state.casefold() else GOLD)
    _text(d, (405, 683), state, size=21, max_width=135,
          color=status_color)

    scaled = im.convert("RGB").resize(
        (1080, round(1080 * im.height / im.width)),
        Image.Resampling.LANCZOS,
    )
    buf = io.BytesIO()
    scaled.save(buf, "PNG", optimize=True)
    return buf.getvalue()
