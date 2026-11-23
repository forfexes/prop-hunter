"""Render 2-6 real ladder prices for ONE athlete on the user's clean original.

The source is separately cleaned and keeps the owner's unchanged logo,
lighting, violet/cyan borders and footer. No old screenshot is painted over.
"""
from __future__ import annotations

import io
import re

from PIL import Image, ImageDraw

from prop_hunter_owner_clean_single import (
    owner_settlement_state, _text, _floating_team, _verified_time, GOLD, GREEN, RED, WHITE,
)


def _observed_form_windows(form):
    """Always print L5/L10/L15, without inventing missing gamelog samples."""
    raw = str(form or "")
    windows = []
    for n in (5, 10, 15):
        match = re.search(r"\bL" + str(n) + r"\s+(\d+)/(\d+)\b", raw, re.I)
        if match and 0 <= int(match[1]) <= int(match[2]) <= n and int(match[2]) > 0:
            windows.append(f"L{n} {match[1]}/{match[2]}")
        else:
            windows.append(f"L{n} —")
    return " · ".join(windows)


def render(plate: Image.Image, *, subtitle: str, teams: list,
           rows: list, footer: str, settlement: str, title: str = "LADDER") -> bytes:
    if plate.size != (691, 865) or len(teams) != 2 or not 2 <= len(rows) <= 6:
        raise ValueError("Original Ladder requires clean plate, two clubs, 2-6 verified legs")
    names = {str(row.get("name") or "").strip().casefold() for row in rows}
    if len(names) != 1 or not next(iter(names)):
        raise ValueError("Ladder has multiple athletes or no confirmed athlete")

    from prop_hunter_original_compositor import _background_portrait
    im = plate.convert("RGBA").copy()
    extra = 0
    if len(rows) == 6:
        # Insert only an EMPTY stadium band from the same owner image, keep
        # the uploaded original crown and footer byte-for-byte in place.
        extra, cut = 120, 730
        original = im
        extended = Image.new("RGBA", (691, 865 + extra), (3, 15, 29, 255))
        extended.paste(original.crop((0, 0, 691, cut)), (0, 0))
        extended.paste(original.crop((0, 515, 691, 635)), (0, cut))
        extended.paste(original.crop((0, cut, 691, 865)),
                       (0, cut + extra))
        im = extended
    for center, team in zip((181, 401), teams):
        _floating_team(im, team, center)
    if not _background_portrait(im, rows[0].get("photo"), (0, 268, 237, 622)):
        raise ValueError("Ladder requires one real transparent athlete cutout")

    date, clock = _verified_time(subtitle)
    d = ImageDraw.Draw(im)
    _text(d, (592, 167), date, size=17, max_width=178, color=GOLD)
    _text(d, (592, 207), clock + " Uhr" if clock else "",
          size=18, max_width=176)
    heading = ("SAME PLAYER · " + str(len(rows)) + " PROPS"
               if title == "SAME PLAYER"
               else str(len(rows)) + " STUFEN")
    _text(d, (448, 305), heading,
          size=25, max_width=240, color=GOLD)
    _text(d, (443, 332), rows[0]["name"], size=23, max_width=335)
    top = (354 + (5 - len(rows)) * 18) if len(rows) <= 5 else 360

    # Translucent data-first layout boxes are built on EMPTY arena artwork.
    # Unlike the legacy compositor, they never cover an old tip or player.
    tint = Image.new("RGBA", im.size, (0, 0, 0, 0))
    p = ImageDraw.Draw(tint)
    for i in range(len(rows)):
        y = top + i * 60
        p.rounded_rectangle((257, y, 673, y + 53), radius=10,
                            fill=(4, 20, 37, 150),
                            outline=(55, 208, 241, 220), width=2)
    im = Image.alpha_composite(im, tint)
    d = ImageDraw.Draw(im)

    for i, row in enumerate(rows, 1):
        y = top + (i - 1) * 60
        _text(d, (277, y + 26), f"{i}.", size=21,
              max_width=33, color=GOLD)
        _text(d, (405, y + 21), row.get("label"),
              size=20, max_width=228)
        # Every line has its OWN verified hit counts. Showing only the
        # first threshold's form in the footer wrongly implies that all
        # priced ladder lines have identical L5/L10/L15 performance.
        _text(d, (378, y + 43), _observed_form_windows(row.get("form")),
              size=12, max_width=235, color=GREEN)
        result = str(row.get("result") or "")
        if result:
            # Each rung has an independent, observed result. Support English
            # source settlement codes while preserving real measured values,
            # instead of treating a real WON/LOST as unknown gold ink.
            state_label, state_color = owner_settlement_state(
                result, green=GREEN, red=RED, white=WHITE)
            # Keep the per-rung settlement outside its left-side form
            # statistics; the bookmaker price remains on the top-right.
            _text(d, (562, y + 43), state_label, size=11,
                  max_width=112, color=state_color)
        _text(d, (618, y + 21), row.get("odds"),
              size=20, max_width=99, color=GOLD)

    # Owner request: athlete is identified ONCE at (443, 332), above the
    # rung list. Do not repeat his name under the portrait at the bottom.
    stake = re.search(r"Einsatz\s+([\d.,]+u)", str(footer or ""), re.I)
    _text(d, (583, 697 + extra),
          "EINSATZ " + stake.group(1) if stake else "",
          size=20, max_width=190, color=GOLD)

    # L5/L10/L15 is already printed within each respective rung above.
    # Leave the stadium floor clear; no oversized duplicate green caption.

    state, color = owner_settlement_state(
        settlement, green=GREEN, red=RED, white=WHITE)
    _text(d, (422, 784 + extra), state, size=21, max_width=148, color=color)

    output = im.convert("RGB").resize(
        (1080, round(1080 * im.height / im.width)),
        Image.Resampling.LANCZOS,
    )
    buf = io.BytesIO()
    output.save(buf, "PNG", optimize=True)
    return buf.getvalue()
