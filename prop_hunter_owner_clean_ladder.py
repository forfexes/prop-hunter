"""Render 2-5 real ladder prices for ONE athlete on the user's clean original.

The source is separately cleaned and keeps the owner's unchanged logo,
lighting, violet/cyan borders and footer. No old screenshot is painted over.
"""
from __future__ import annotations

import io
import re

from PIL import Image, ImageDraw

from prop_hunter_owner_clean_single import (
    _text, _floating_team, _verified_time, GOLD, GREEN, RED,
)


def render(plate: Image.Image, *, subtitle: str, teams: list,
           rows: list, footer: str, settlement: str) -> bytes:
    if plate.size != (691, 865) or len(teams) != 2 or not 2 <= len(rows) <= 5:
        raise ValueError("Original Ladder requires clean plate, two clubs, 2-5 stages")
    names = {str(row.get("name") or "").strip().casefold() for row in rows}
    if len(names) != 1 or not next(iter(names)):
        raise ValueError("Ladder has multiple athletes or no confirmed athlete")

    from prop_hunter_original_compositor import _background_portrait
    im = plate.convert("RGBA").copy()
    for center, team in zip((181, 401), teams):
        _floating_team(im, team, center)
    if not _background_portrait(im, rows[0].get("photo"), (0, 268, 237, 622)):
        raise ValueError("Ladder requires one real transparent athlete cutout")

    date, clock = _verified_time(subtitle)
    d = ImageDraw.Draw(im)
    _text(d, (592, 167), date, size=17, max_width=178, color=GOLD)
    _text(d, (592, 207), clock + " Uhr" if clock else "",
          size=18, max_width=176)
    _text(d, (448, 305), str(len(rows)) + " STUFEN",
          size=25, max_width=240, color=GOLD)
    _text(d, (443, 332), rows[0]["name"], size=23, max_width=335)
    top = 342 + (5 - len(rows)) * 18

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
        form = str(row.get("form") or "")
        hit = re.search(r"\bL15\s+(\d+)/(\d+)\b", form, re.I)
        if hit and 0 <= int(hit[1]) <= int(hit[2]) <= 15:
            _text(d, (374, y + 43), "L15 " + hit[0].split()[-1],
                  size=12, max_width=140, color=GREEN)
        result = str(row.get("result") or "")
        if result:
            state_color = (GREEN if "gewonnen" in result.casefold()
                           else RED if "verloren" in result.casefold() else GOLD)
            _text(d, (529, y + 43), result, size=11,
                  max_width=132, color=state_color)
        _text(d, (618, y + 21), row.get("odds"),
              size=20, max_width=99, color=GOLD)

    _text(d, (127, 650), rows[0]["name"], size=21, max_width=220)
    stake = re.search(r"Einsatz\s+([\d.,]+u)", str(footer or ""), re.I)
    _text(d, (583, 697),
          "EINSATZ " + stake.group(1) if stake else "",
          size=20, max_width=190, color=GOLD)

    # Form windows belong to the ONE actual athlete. Stages retain their own
    # per-threshold L15 row without copying an unrelated player form.
    form = str(rows[0].get("form") or "")
    windows = []
    for n in (5, 10, 15):
        match = re.search(r"\bL" + str(n) + r"\s+(\d+)/(\d+)\b", form, re.I)
        if match and 0 <= int(match[1]) <= int(match[2]) <= n:
            windows.append(f"L{n} {match[1]}/{match[2]}")
    _text(d, (374, 681), " · ".join(windows),
          size=17, max_width=359, color=GREEN)

    state = str(settlement or "OFFEN").strip()
    color = (GREEN if "gewonnen" in state.casefold()
             else RED if "verloren" in state.casefold() else GOLD)
    _text(d, (422, 784), state, size=21, max_width=148, color=color)

    output = im.convert("RGB").resize(
        (1080, round(1080 * im.height / im.width)),
        Image.Resampling.LANCZOS,
    )
    buf = io.BytesIO()
    output.save(buf, "PNG", optimize=True)
    return buf.getvalue()
