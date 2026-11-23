"""Layered 2-7 leg Builder on the owner's truly cleaned original artwork.

No opaque masking of old example players/fixtures/prices. Seven legs means
seven separately verified athletes and seven visible, independently priced rows.
"""
from __future__ import annotations

import io
import re

from PIL import Image, ImageDraw

from prop_hunter_owner_clean_single import (
    owner_settlement_state, _text, _verified_time, _place_authentic_crest,
    GOLD, GREEN, RED, WHITE,
)


def _team(im, team, cx, *, shift=0):
    if (not team or not str(team[0] or "").strip()
            or not isinstance(team[1], Image.Image)):
        raise ValueError("Verified team name and genuine logo required")
    _place_authentic_crest(im, team[1], cx, 442 + shift, 52)
    _text(ImageDraw.Draw(im), (cx, 487 + shift),
          team[0], size=16, max_width=175)


def _form_label(raw, all_windows=False):
    """Actual L5/L10/L15 per athlete. Missing samples are unknown, never 0/0."""
    fields = []
    for n in (5, 10, 15):
        match = re.search(
            r"\bL" + str(n) + r"\s+(\d+)/(\d+)\b", str(raw or ""), re.I
        )
        if match and 0 <= int(match[1]) <= int(match[2]) <= n and int(match[2]) > 0:
            fields.append(f"L{n} {match[1]}/{match[2]}")
        else:
            fields.append(f"L{n} —")
    return " · ".join(fields if all_windows else fields[-1:])


def _extend_owner_clean_builder(plate: Image.Image, count: int):
    """Only for 8-10: grow the actual cleaned owner's arena in two clear zones.

    No image/text is drawn over a completed screenshot. The crown/logo,
    owner footer, club badges and betting ticket remain pixel-preserved;
    empty arena-only sample-free scanlines bridge the extra height.
    """
    portrait_extra = 190 if count > 7 else 0
    ticket_extra = max(0, count * 32 - 177 + 12) if count > 7 else 0
    if not portrait_extra:
        return plate.convert("RGBA").copy(), 0, 0
    cut1, cut2 = 365, 625
    original = plate.convert("RGBA")
    canvas = Image.new("RGBA",
                       (original.width, original.height + portrait_extra + ticket_extra),
                       (4, 16, 31, 255))
    canvas.alpha_composite(original.crop((0, 0, original.width, cut1)), (0, 0))

    def blended_empty_band(cut: int, height: int):
        # Only rows on either side of a blank original-source stadium/ticket
        # region contribute. Interpolate, rather than repeat a strip of the
        # owner's cyan border/glow over multiple rows.
        upper = original.crop((0, cut-1, original.width, cut)).resize(
            (original.width, height))
        lower = original.crop((0, cut, original.width, cut+1)).resize(
            (original.width, height))
        mask = Image.linear_gradient("L").resize(
            (original.width, height), Image.Resampling.BILINEAR)
        return Image.composite(lower, upper, mask)

    canvas.alpha_composite(
        blended_empty_band(cut1, portrait_extra), (0, cut1))
    canvas.alpha_composite(
        original.crop((0, cut1, original.width, cut2)),
        (0, cut1 + portrait_extra))
    canvas.alpha_composite(
        blended_empty_band(cut2, ticket_extra),
        (0, cut2 + portrait_extra))
    canvas.alpha_composite(
        original.crop((0, cut2, original.width, original.height)),
        (0, cut2 + portrait_extra + ticket_extra))
    return canvas, portrait_extra, ticket_extra


def render(plate: Image.Image, *, subtitle: str, teams: list,
           rows: list, footer: str, settlement: str) -> bytes:
    if plate.size != (691, 867) or len(teams) != 2 or not 2 <= len(rows) <= 10:
        raise ValueError("Clean original Builder needs 2-10 verified legs and two teams")
    for i, row in enumerate(rows, 1):
        if (not isinstance(row.get("photo"), Image.Image)
                or not all(str(row.get(k) or "").strip()
                           for k in ("name", "label", "odds"))):
            raise ValueError(f"Builder leg {i}: genuine player/market/price missing")

    from prop_hunter_original_compositor import _background_portrait
    n = len(rows)
    im, portrait_extra, ticket_extra = _extend_owner_clean_builder(plate, n)
    centers = [195, 493] if n == 2 else [117, 345, 573]

    # All selected athletes are rendered as real alpha-cutout image layers.
    # No rectangular portraits, no reuse of one photo for another player.
    for i, row in enumerate(rows):
        cx = centers[i % len(centers)]
        if n <= 3:
            rect = (cx - 103, 139, cx + 103, 335)
        elif n <= 6:
            top = 133 + (i // 3) * 130
            rect = (cx - 72, top, cx + 72, top + 90)
        elif n <= 7:
            top = 129 + (i // 3) * 91
            rect = (cx - 63, top, cx + 63, top + 65)
        else:
            top = 125 + (i // 3) * 97
            rect = (cx - 60, top, cx + 60, top + 69)
        if not _background_portrait(im, row["photo"], rect):
            raise ValueError(f"Builder leg {i+1}: authentic alpha cutout required")

    for cx, team in zip((213, 476), teams):
        _team(im, team, cx, shift=portrait_extra)
    d = ImageDraw.Draw(im)
    # Keep portraits free of repeated names and betting selections.
    # The full player and market appear ONCE, in the numbered ticket below.
    # Only independently observed recent form may sit beneath a portrait.
    if n <= 3:
        for row, cx in zip(rows, centers):
            _text(d, (cx, 387), _form_label(row.get("form"), True),
                  size=12, max_width=202, color=GREEN)
    elif n <= 6:
        for i, row in enumerate(rows):
            cx = centers[i % 3]
            top = 133 + (i // 3) * 130
            _text(d, (cx, top + 108), _form_label(row.get("form"), True),
                  size=11, max_width=202, color=GREEN)
    elif n <= 7:
        for i, row in enumerate(rows):
            cx = centers[i % 3]
            top = 129 + (i // 3) * 91
            _text(d, (cx, top + 78), _form_label(row.get("form"), True),
                  size=10, max_width=198, color=GREEN)
    else:
        for i, row in enumerate(rows):
            cx = centers[i % 3]
            top = 125 + (i // 3) * 97
            _text(d, (cx, top + 81), _form_label(row.get("form"), True),
                  size=10, max_width=198, color=GREEN)

    date, clock = _verified_time(subtitle)
    _text(d, (344, 506 + portrait_extra), (date + " · " + clock).strip(" ·"),
          size=15, max_width=438, color=WHITE)

    # Create transparent data slots on the original empty cyan ticket area.
    # Previously these boxes hid old samples from a screenshot at runtime.
    start = 531 + portrait_extra
    row_step = (177 + ticket_extra) / n
    tint = Image.new("RGBA", im.size, (0, 0, 0, 0))
    p = ImageDraw.Draw(tint)
    for i in range(n):
        y = round(start + i * row_step)
        p.rounded_rectangle(
            (37, y, 654, y + max(21, round(row_step) - 3)),
            radius=7, fill=(3, 18, 36, 134),
            outline=(40, 183, 230, 205), width=1,
        )
    im = Image.alpha_composite(im, tint)
    d = ImageDraw.Draw(im)
    for i, row in enumerate(rows, 1):
        yy = round(start + (i - 0.5) * row_step) + 1
        # Show the real settlement of each leg in the EXISTING number slot;
        # do not cover any name, price or approved original artwork.
        from prop_hunter_owner_leg_status import leg_result_mark
        marker, status = leg_result_mark(i, row.get("result"))
        tone = GREEN if status == "won" else RED if status == "lost" else GOLD
        _text(d, (55, yy), marker, size=16 if n < 7 else 13,
              max_width=30, color=tone)
        _text(d, (181, yy), row.get("name"),
              size=16 if n < 6 else 12, max_width=180)
        _text(d, (430, yy), row.get("label"),
              size=16 if n < 6 else 12, max_width=260, color=GOLD)
        _text(d, (605, yy), row.get("odds"),
              size=17 if n < 6 else 13, max_width=81, color=GREEN)

    _text(d, (182, 754+portrait_extra+ticket_extra), f"{n}-LEG BUILDER", size=24, max_width=291)
    # Rendering a calculated leg-product as gold '@xx' misrepresents it as
    # an available BOOKMAKER ticket. This must fail closed even when callers
    # bypass the approved NBA bridge. Synthetic offline image QA can leave
    # the price unknown ("—"), but must never invent a combined quote.
    if re.search(r"\b(?:Berechnet|estimated|calculated)\b",
                 str(footer or ""), re.I):
        raise ValueError("Calculated Builder quote is not an observed bookmaker price")
    quote = re.search(r"\bQuote\s+@?([\d.,]+)\b",
                      str(footer or ""), re.I)
    _text(d, (445, 746+portrait_extra+ticket_extra), "@" + quote.group(1) if quote else "—",
          size=23, max_width=107, color=GOLD)
    stake = re.search(r"Einsatz\s+([\d.,]+u)", str(footer or ""), re.I)
    _text(d, (599, 746+portrait_extra+ticket_extra), stake.group(1) if stake else "—",
          size=22, max_width=95, color=GOLD)
    state, color = owner_settlement_state(
        settlement, green=GREEN, red=RED, white=WHITE)
    # Owner-approved footer: a single floating AUSWERTUNG / status line,
    # WHITE when pending, without any extra sticker or opaque rectangle.
    # The sample-free stadium below the real quote has room for this text.
    _text(d, (350, 786+portrait_extra+ticket_extra), "AUSWERTUNG: " + state,
          size=17, max_width=355, color=color)

    output = im.convert("RGB").resize(
        (1080, round(1080 * im.height / im.width)),
        Image.Resampling.LANCZOS,
    )
    buf = io.BytesIO()
    output.save(buf, "PNG", optimize=True)
    return buf.getvalue()
