"""Render a PROP HUNTER Single on the owner's already cleaned bitmap.

No opaque cover-up of a screenshot or fallback poster. This module does not
publish to Telegram or authorize the use of an unfinished source plate.
"""
from __future__ import annotations

import io
import re

from PIL import Image, ImageDraw, ImageFont

DARK_GREEN = (3, 20, 25, 255)  # OPAQUE: never show old arena/player through odds text
DARK_GOLD = (27, 20, 7, 255)  # OPAQUE: bookmaker price must not show through
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
          color=WHITE, anchor="mm", stroke_width=0, stroke_fill=None):
    value = str(value or "").strip()
    if not value:
        return
    font = _font(size)
    while size > 11 and draw.textlength(value, font=font) > max_width:
        size -= 1
        font = _font(size)
    if draw.textlength(value, font=font) > max_width:
        raise ValueError("Owner Single text too long for its actual source slot")
    draw.text(position, value, fill=color, font=font, anchor=anchor,
              stroke_width=stroke_width, stroke_fill=stroke_fill)


def owner_settlement_state(raw, *, green, red, white):
    """Return (display, ink) without inferring results from model confidence.

    Mixed winning/losing original Builder & Lottery tickets must NOT be green.
    Counted 0 losses are not losses, and any unsettled leg stays neutral.
    """
    original = str(raw or "OFFEN").strip() or "OFFEN"
    canonical = {
        "won": "GEWONNEN", "win": "GEWONNEN",
        "lost": "VERLOREN", "loss": "VERLOREN",
        "pending": "OFFEN", "open": "OFFEN",
        "void": "VOID", "push": "PUSH",
    }
    state = canonical.get(original.casefold(), original)
    normalized = state.casefold()
    counts = re.findall(r"\b(\d+)\s+(gewonnen|verloren|offen|push|void)\b", normalized)
    if counts:
        by_kind = {}
        for number, label in counts:
            by_kind[label] = by_kind.get(label, 0) + int(number)
        if by_kind.get("verloren", 0) > 0:
            return state, red
        if by_kind.get("offen", 0) > 0:
            return state, white
        if by_kind.get("gewonnen", 0) > 0:
            return state, green
        return state, white
    if re.search(r"\b(verloren|lost|loss)\b", normalized):
        return state, red
    if re.search(r"\b(offen|pending|open|void|push)\b", normalized):
        return state, white
    if re.search(r"\b(gewonnen|won|win)\b", normalized):
        return state, green
    return state, white


def _fit_authentic_crest(source: Image.Image, diameter: int) -> Image.Image:
    """Trim unused transparent padding; keep the REAL logo's proportions.

    This emblem floats freely on the clean owner stadium: no disk, ring,
    opaque rectangle, painted backing, or synthetic badge may be added.
    """
    if not isinstance(source, Image.Image) or diameter < 1:
        raise ValueError("Authentic team crest required")
    icon = source.convert("RGBA")
    alpha = icon.getchannel("A")
    # A rectangular JPEG/PNG with a white photographic background becomes
    # a visibly pasted-on sticker; do not fabricate a transparent cutout.
    # The original downloaded emblem must already have transparent pixels.
    if alpha.getextrema()[0] >= 255:
        raise ValueError("Opaque crest sticker rejected: original transparency required")
    visible = alpha.point(lambda a: 255 if a >= 24 else 0).getbbox()
    if visible is None:
        raise ValueError("Team crest contains no visible artwork")
    icon = icon.crop(visible)
    if min(icon.size) < 12:
        raise ValueError("Team crest visible artwork too small")
    # The real emblem, not its transparent provider canvas, must fill the
    # existing owner ring. thumbnail() never enlarges a small source crest.
    scale = diameter / max(icon.size)
    if scale > 4:
        raise ValueError("Team crest source resolution too low for premium image")
    size = (max(1, round(icon.width * scale)),
            max(1, round(icon.height * scale)))
    return icon.resize(size, Image.Resampling.LANCZOS)


def _place_authentic_crest(im: Image.Image, source: Image.Image,
                          cx: int, cy: int, diameter: int) -> None:
    """One logo, centred horizontally AND vertically in the original slot."""
    icon = _fit_authentic_crest(source, diameter)
    x = round(cx - icon.width / 2)
    y = round(cy - icon.height / 2)
    im.alpha_composite(icon, (x, y))


def _floating_team(im, team, cx):
    if (not team or not str(team[0] or "").strip()
            or not isinstance(team[1], Image.Image)):
        raise ValueError("Genuine team logo and club name are mandatory")
    name, logo = team
    _place_authentic_crest(im, logo, cx, 186, 71)
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

    # The supplied clean SINGLE master already contains the empty
    # neon market and price rails.  Render ONLY new text on those rails:
    # never paste black/gold rectangles or paint over the owner's artwork.
    # A tiny glyph-level outline keeps type legible without repainting the
    # stadium, the portrait or any of the template's original light effects.
    d = ImageDraw.Draw(im)
    _text(d, (340, 410), row.get("label"), size=27, max_width=236,
          stroke_width=1, stroke_fill=(3, 12, 22))
    _text(d, (547, 410), row.get("odds"), size=27,
          max_width=125, color=GOLD,
          stroke_width=1, stroke_fill=(3, 12, 22))
    _text(d, (159, 476), "LETZTE SPIELE", size=18, max_width=168)
    _observed_form(d, row.get("form"))
    _models(d, row.get("model"))
    amount = re.search(r"Einsatz\s+([\d.,]+u)", str(footer or ""), re.I)
    _text(d, (597, 553), amount.group(1) if amount else "—",
          size=24, max_width=115, color=GOLD)
    # Match the owner's AUSWERTUNG label: one baseline, NO new black/gold
    # sticker or opacity layer. Mixed results and pending legs are not wins.
    state, status_color = owner_settlement_state(
        settlement, green=GREEN, red=RED, white=WHITE)
    _text(d, (405, 669), state, size=21, max_width=135,
          color=status_color)

    scaled = im.convert("RGB").resize(
        (1080, round(1080 * im.height / im.width)),
        Image.Resampling.LANCZOS,
    )
    buf = io.BytesIO()
    scaled.save(buf, "PNG", optimize=True)
    return buf.getvalue()
