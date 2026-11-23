"""Layered original-owner Lottery for 2-12 independently verified NBA games.

The real user-supplied violet stadium's header/footer are preserved. For
large tickets only its CLEAN stadium midsection is extended; no prefilled
screenshot text is hidden with opaque rectangles and no fake single fixture
is substituted for individual leg matchups/tipoffs.
"""
from __future__ import annotations

import io
import re

from PIL import Image, ImageDraw

from prop_hunter_owner_clean_single import (
    owner_settlement_state, _text, GOLD, GREEN, RED, WHITE,
)


def _extended(plate: Image.Image, n: int):
    # Reserve 85 px per verified leg, so L5/L10/L15 and each game's exact
    # date/time stay readable even at 12 legs.
    extra = max(0, n * 85 + 20 - 295)
    if not extra:
        return plate.convert("RGBA").copy(), 0

    src = plate.convert("RGBA")
    width, height = src.size
    cut = 637
    canvas = Image.new("RGBA", (width, height + extra), (3, 15, 29, 255))
    canvas.paste(src.crop((0, 0, width, cut)), (0, 0))
    # A genuinely empty arena band from this SAME owner image is inserted.
    # The top brand, all authentic outlines and bottom footer remain original.
    band = src.crop((0, 445, width, 515))
    for y in range(cut, cut + extra, 70):
        canvas.paste(band, (0, y))
    canvas.paste(src.crop((0, cut, width, height)), (0, cut + extra))
    return canvas, extra


def render(plate: Image.Image, *, rows: list,
           footer: str, settlement: str) -> bytes:
    if plate.size != (691, 753) or not 2 <= len(rows) <= 12:
        raise ValueError("Original Lottery requires clean plate and 2-12 legs")
    for i, row in enumerate(rows, 1):
        if (not isinstance(row.get("photo"), Image.Image)
                or not all(str(row.get(k) or "").strip()
                           for k in ("name", "label", "odds", "game"))):
            raise ValueError(
                f"Lottery leg {i} lacks authentic athlete, market, odds or game"
            )
        game = str(row["game"])
        if (not re.search(r"\s+(?:vs\.?|@)\s+", game, re.I)
                or not re.search(r"\d{2}:\d{2}", game)):
            raise ValueError(
                f"Lottery leg {i} needs independently verified fixture and time"
            )

    from prop_hunter_original_compositor import _background_portrait
    n = len(rows)
    im, extra = _extended(plate, n)
    if not _background_portrait(im, rows[0].get("photo"), (0, 148, 199, 321)):
        raise ValueError("Lottery hero requires real transparent athlete cutout")

    d = ImageDraw.Draw(im)
    _text(d, (349, 302), "MEHRERE SPIELE",
          size=19, max_width=286, color=GOLD)
    _text(d, (603, 149), f"{n} SPIELE",
          size=23, max_width=158, color=WHITE)
    _text(d, (600, 188), "BUCHMACHER-QUOTE",
          size=13, max_width=160, color=GOLD)
    quote = re.search(r"\bQuote\s+@?([\d.,]+)", str(footer or ""), re.I)
    if not quote:
        raise ValueError("Real observed combined bookmaker ticket missing")
    _text(d, (601, 220), "@" + quote.group(1),
          size=28, max_width=161, color=GOLD)

    top = 342 + max(0, (295 - n * 85) // 2)
    tint = Image.new("RGBA", im.size, (0, 0, 0, 0))
    p = ImageDraw.Draw(tint)
    for i in range(n):
        y = top + i * 85
        p.rounded_rectangle(
            (43, y, 648, y + 81), radius=9,
            fill=(21, 10, 34, 146),
            outline=(200, 71, 238, 210), width=2,
        )
    im = Image.alpha_composite(im, tint)
    d = ImageDraw.Draw(im)

    for i, row in enumerate(rows, 1):
        y = top + (i - 1) * 85
        if not _background_portrait(im, row.get("photo"),
                                    (50, y + 6, 97, y + 75)):
            raise ValueError(f"Lottery leg {i}: authentic alpha cutout missing")
        # Exact source result, displayed in the already-reserved leg label.
        # Do NOT overlay the original footer or overwrite any game's odds.
        from prop_hunter_owner_leg_status import leg_result_mark
        marker, status = leg_result_mark(i, row.get("result"))
        tone = GREEN if status == "won" else RED if status == "lost" else WHITE
        _text(d, (111, y + 16), f"{marker} {row['name']}",
              size=17, max_width=232, anchor="lm", color=tone)
        _text(d, (339, y + 36), row["label"],
              size=16, max_width=452, color=GOLD)
        _text(d, (345, y + 56), row["game"],
              size=12, max_width=452, color=WHITE)
        _text(d, (594, y + 16), row["odds"],
              size=19, max_width=94, color=GREEN)
        # Every cross-game selection gets its OWN observed form window.
        # The runner may have no real gamelog for one athlete; write "—"
        # instead of leaving a misleading blank row or copying another leg.
        from prop_hunter_owner_clean_ladder import _observed_form_windows
        _text(d, (346, y + 75), _observed_form_windows(row.get("form")),
              size=12, max_width=445, color=GREEN)

    stake = re.search(r"Einsatz\s+([\d.,]+u)", str(footer or ""), re.I)
    _text(d, (585, 644 + extra),
          "EINSATZ " + stake.group(1) if stake else "",
          size=18, max_width=183, color=GOLD)
    state, color = owner_settlement_state(
        settlement, green=GREEN, red=RED, white=WHITE)
    _text(d, (405, 673 + extra), state,
          size=20, max_width=150, color=color)

    output = im.convert("RGB").resize(
        (1080, round(1080 * im.height / im.width)),
        Image.Resampling.LANCZOS,
    )
    buf = io.BytesIO()
    output.save(buf, "PNG", optimize=True)
    return buf.getvalue()
