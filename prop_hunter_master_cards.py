"""PROP HUNTER cards drawn from code on the owner's clean arena master.

No baked screenshots, no opaque patches, no placeholder dashes: every value
shown comes from the row data; a missing window/metric is simply not drawn.
The Telegram handle never appears in the image (it is sent as caption text).
Fails closed (ValueError) when a real photo, crest, quote or name is missing.
"""
from __future__ import annotations

import io
import re
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent
MASTER = ROOT / "assets" / "prop_hunter_arena_master.png"
W, H = 1080, 1440
CYAN, GOLD, GREEN, RED, WHITE = (60, 200, 255), (255, 205, 70), (60, 235, 140), (255, 90, 90), (245, 248, 255)
NAVY = (5, 14, 30)
_FONTS = ("/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-BoldOblique.ttf",
          "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


def _font(size, oblique=True):
    for path in (_FONTS if oblique else _FONTS[1:]):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


@lru_cache(maxsize=1)
def _master_bytes():
    if not MASTER.is_file():
        raise ValueError("Prop Hunter arena master missing")
    with Image.open(MASTER) as im:
        if im.size != (W, H):
            raise ValueError("Prop Hunter arena master has wrong size")
        return im.convert("RGBA").tobytes()


def _canvas():
    return Image.frombytes("RGBA", (W, H), _master_bytes())


def _text(d, xy, text, max_w, size, fill=WHITE, anchor="mm", min_size=14, oblique=True):
    value = " ".join(str(text if text is not None else "").split())
    if not value or any(ord(c) < 32 for c in value):
        raise ValueError("Missing or invalid card text")
    for s in range(size, min_size - 1, -1):
        f = _font(s, oblique)
        box = d.textbbox((0, 0), value, font=f, anchor="lm")
        if box[2] - box[0] <= max_w:
            d.text(xy, value, font=f, fill=fill, anchor=anchor)
            return
    raise ValueError("Text too long for slot: " + value[:40])


def _panel(im, box, color=CYAN, radius=22, fill=(4, 12, 26, 205), glow=18, width=3):
    x0, y0, x1, y1 = box
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle(box, radius, outline=color + (255,), width=width + 3)
    im.alpha_composite(layer.filter(ImageFilter.GaussianBlur(glow / 2)))
    d = ImageDraw.Draw(im, "RGBA")
    d.rounded_rectangle(box, radius, fill=fill, outline=color + (255,), width=width)


def _gold_pill(im, box, skew=36):
    x0, y0, x1, y1 = box
    pts = [(x0 + skew, y0), (x1, y0), (x1 - skew, y1), (x0, y1)]
    glow = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(glow).polygon(pts, fill=GOLD + (200,))
    im.alpha_composite(glow.filter(ImageFilter.GaussianBlur(14)))
    d = ImageDraw.Draw(im, "RGBA")
    d.polygon(pts, fill=(255, 196, 40, 255), outline=(255, 238, 160, 255))
    d.line([(x0 + skew + 8, y0 + 6), (x1 - 8, y0 + 6)], fill=(255, 245, 190, 255), width=2)


def _rgba(source, what):
    if isinstance(source, (bytes, bytearray)):
        source = Image.open(io.BytesIO(source))
    if not isinstance(source, Image.Image):
        raise ValueError(f"Real {what} required")
    return source.convert("RGBA")


def _crest(im, source, center, size):
    img = _rgba(source, "team crest")
    a = img.getchannel("A")
    box = a.point(lambda v: 255 if v >= 24 else 0).getbbox()
    if box is None or min(box[2] - box[0], box[3] - box[1]) < 24:
        raise ValueError("Team crest has no visible emblem")
    if a.getextrema()[0] >= 250:
        w, h = img.size
        c = [img.getpixel(p)[:3] for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))]
        if max(max(abs(p - q) for p, q in zip(c[0], x)) for x in c) <= 12:
            raise ValueError("opaque rectangular crest tile is not a genuine crest")
    img = img.crop(box)
    f = min(size / img.width, size / img.height)
    if f > 4:
        raise ValueError("Crest resolution too small")
    img = img.resize((max(1, round(img.width * f)), max(1, round(img.height * f))), Image.Resampling.LANCZOS)
    shadow = Image.new("RGBA", im.size, (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 150), (center[0] - img.width // 2, center[1] - img.height // 2 + 6), img.getchannel("A"))
    im.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(10)))
    im.alpha_composite(img, (center[0] - img.width // 2, center[1] - img.height // 2))


def _cutout(im, source, box, align="bottom"):
    """Frameless real player cutout fitted inside box, feet/shoulders on its bottom edge."""
    img = _rgba(source, "player photo")
    a = img.getchannel("A")
    if a.getextrema()[0] >= 250:
        raise ValueError("Player photo must be a real transparent cutout")
    bb = a.point(lambda v: 255 if v >= 24 else 0).getbbox()
    if bb is None:
        raise ValueError("Player photo is empty")
    img = img.crop(bb)
    x0, y0, x1, y1 = box
    f = min((x1 - x0) / img.width, (y1 - y0) / img.height)
    if f > 3:
        raise ValueError("Player photo resolution too small")
    img = img.resize((max(1, round(img.width * f)), max(1, round(img.height * f))), Image.Resampling.LANCZOS)
    x = x0 + (x1 - x0 - img.width) // 2
    y = y1 - img.height
    im.alpha_composite(img, (x, y))


def _odds(value):
    m = re.search(r"\d+(?:[.,]\d+)?", str(value or ""))
    if not m:
        raise ValueError("Real bookmaker quote required")
    v = float(m.group(0).replace(",", "."))
    if not 1.01 <= v <= 1000:
        raise ValueError("Bookmaker quote out of range")
    return f"@{v:.2f}"


def _windows(form):
    out = []
    for n in (5, 10, 15):
        m = re.search(rf"\bL{n}\s*(\d+/\d+)", str(form or ""), re.I)
        if m:
            out.append((f"L{n}", m.group(1)))
    return out


def _state(settlement):
    s = str(settlement or "OFFEN").strip()
    low = s.lower()
    if "verloren" in low or low.startswith("-"):
        return s.upper(), RED
    if "gewonnen" in low:
        return s.upper(), GREEN
    return s.upper() or "OFFEN", GOLD


def _head(im, kind_label):
    d = ImageDraw.Draw(im, "RGBA")
    _text(d, (540, 92), "PROP HUNTER", 640, 96, WHITE)
    d.line([(300, 148), (780, 148)], fill=GOLD + (255,), width=3)
    _gold_pill(im, (230, 168, 850, 252))
    _text(ImageDraw.Draw(im), (540, 210), kind_label, 520, 52, (14, 10, 0))


def _teams(im, teams, y, size, show_names=True):
    if len(teams) != 2:
        raise ValueError("Exactly two verified teams required")
    d = ImageDraw.Draw(im, "RGBA")
    (hn, hl), (an, al) = teams
    _crest(im, hl, (270, y), size)
    _crest(im, al, (810, y), size)
    d = ImageDraw.Draw(im, "RGBA")
    _text(d, (540, y), "VS", 160, 76, GOLD)
    if show_names:
        _text(d, (270, y + size // 2 + 38), hn, 380, 34)
        _text(d, (810, y + size // 2 + 38), an, 380, 34)


def _when(im, subtitle, y):
    from prop_hunter_original_compositor import _panel_fields
    date_s, time_s, _v1, _v2 = _panel_fields(subtitle)
    bits = [b for b in (date_s, time_s) if b]
    if not bits:
        return False
    _panel(im, (300, y, 780, y + 66), CYAN, 18)
    _text(ImageDraw.Draw(im), (540, y + 33), "  ·  ".join(bits), 440, 34, GOLD)
    return True


def _foot(im, y, settlement):
    label, col = _state(settlement)
    _panel(im, (170, y, 910, y + 84), GOLD, 22)
    d = ImageDraw.Draw(im)
    _text(d, (540, y + 42), f"AUSWERTUNG   {label}", 680, 42, col)


def _png(im):
    out = io.BytesIO()
    im.convert("RGB").save(out, "PNG", optimize=True)
    return out.getvalue()


def _need(row, key):
    v = row.get(key)
    if v is None or str(v).strip() == "":
        raise ValueError(f"Verified {key} missing")
    return v


def render_single(title, subtitle, teams, row, footer="", settlement="OFFEN"):
    im = _canvas()
    _head(im, "PRO TIP — SINGLE")
    _teams(im, teams, 400, 190)
    _when(im, subtitle, 590)
    name, label, odds = str(_need(row, "name")), str(_need(row, "label")), _odds(row.get("odds"))
    _cutout(im, row.get("photo"), (20, 640, 470, 1030))
    _panel(im, (440, 668, 1050, 760), GOLD, 22)
    d = ImageDraw.Draw(im)
    _text(d, (745, 714), name, 560, 46)
    market = str(title or "").strip()
    if market and market.upper() not in ("SINGLE", "PRO TIP — SINGLE"):
        _text(d, (745, 800), market.upper(), 560, 30, CYAN)
    _panel(im, (440, 830, 800, 930), GREEN, 22, fill=(4, 44, 35, 220))
    _text(ImageDraw.Draw(im), (620, 880), label, 330, 40)
    _panel(im, (820, 830, 1050, 930), GOLD, 22, fill=(65, 39, 5, 225))
    _text(ImageDraw.Draw(im), (935, 880), odds, 200, 46, GOLD)
    # Statistic panels: only real windows / metrics / stake.
    panels = []
    form = _windows(row.get("form"))
    if form:
        panels.append(("FORM & STATS", [(a, b, GREEN) for a, b in form]))
    model = row.get("model") or {}
    metrics = []
    if model.get("prob"):
        metrics.append(("PROB", f"{model['prob']}%", GREEN))
    if model.get("edge"):
        metrics.append(("EDGE", f"{model['edge']}%", GREEN))
    if model.get("confidence"):
        metrics.append(("CONF", str(model["confidence"]), GREEN))
    if metrics:
        panels.append(("MODELL", metrics))
    stake = re.search(r"Einsatz\s+([\d.,]+u)", str(footer), re.I)
    if stake:
        panels.append(("EINSATZ", [("", stake.group(1), GOLD)]))
    if panels:
        step = 1000 / len(panels)
        for i, (head, lines) in enumerate(panels):
            x0 = 40 + i * step
            box = (round(x0 + 8), 1060, round(x0 + step - 8), 1250)
            _panel(im, box, CYAN, 22)
            dd = ImageDraw.Draw(im)
            cx = (box[0] + box[2]) // 2
            _text(dd, (cx, 1090), head, box[2] - box[0] - 40, 30, WHITE)
            gap = 150 / (len(lines) + 0.4)
            for j, (a, b, col) in enumerate(lines):
                yy = round(1130 + gap * (j + 0.3))
                if a:
                    _text(dd, (box[0] + 28, yy), a, 120, 28, WHITE, "lm")
                    _text(dd, (box[2] - 28, yy), b, box[2] - box[0] - 150, 30, col, "rm")
                else:
                    _text(dd, (cx, yy + 6), b, box[2] - box[0] - 50, 46, col)
    _foot(im, 1290, settlement)
    return _png(im)


def render_ladder(title, subtitle, teams, rows, footer="", settlement="OFFEN"):
    names = {str(r.get("name") or "").strip().casefold() for r in rows}
    if len(names) != 1 or not next(iter(names)):
        raise ValueError("Ladder must use exactly one real athlete")
    if not 2 <= len(rows) <= 6:
        raise ValueError("Ladder supports 2-6 rungs")
    im = _canvas()
    _head(im, "PRO TIP — LADDERS")
    _teams(im, teams, 365, 150, show_names=False)
    d = ImageDraw.Draw(im, "RGBA")
    _text(d, (270, 365 + 105), teams[0][0], 380, 30)
    _text(d, (810, 365 + 105), teams[1][0], 380, 30)
    _when(im, subtitle, 510)
    _cutout(im, rows[0].get("photo"), (10, 610, 400, 1180))
    _panel(im, (30, 1100, 390, 1170), CYAN, 18)
    _text(ImageDraw.Draw(im), (210, 1135), str(rows[0]["name"]), 330, 34)
    n = len(rows)
    rh = min(150, 600 // n)
    top = 610 + (600 - rh * n) // 2
    for i, r in enumerate(rows):
        y = top + i * rh
        _panel(im, (420, y, 1050, y + rh - 14), CYAN, 20)
        dd = ImageDraw.Draw(im)
        _text(dd, (452, y + 30), f"{i + 1}. STUFE", 160, 24, GOLD, "lm")
        _text(dd, (452, y + (rh - 14) // 2 + 10), str(_need(r, "label")), 360, 38, WHITE, "lm")
        _text(dd, (1020, y + (rh - 14) // 2 - 2), _odds(r.get("odds")), 200, 44, GOLD, "rm")
        w = _windows(r.get("form"))
        if w:
            _text(dd, (1020, y + rh - 14 - 26), "  ".join(f"{a} {b}" for a, b in w), 330, 22, GREEN, "rm")
        res = str(r.get("result") or "").strip()
        if res:
            col = RED if "VERLOREN" in res.upper() else GREEN if "GEWONNEN" in res.upper() else WHITE
            _text(dd, (452, y + rh - 14 - 26), res, 220, 22, col, "lm")
    stake = re.search(r"Einsatz\s+([\d.,]+u)", str(footer), re.I)
    if stake:
        _panel(im, (690, 1218, 1050, 1276), GOLD, 16)
        _text(ImageDraw.Draw(im), (870, 1247), f"EINSATZ {stake.group(1)}", 320, 30, GOLD)
    _foot(im, 1296, settlement)
    return _png(im)


def render_list(kind, title, subtitle, teams, rows, footer="", settlement="OFFEN"):
    """Builder / lottery: one row per verified leg with its real portrait."""
    if not 2 <= len(rows) <= 6:
        raise ValueError("Master list card supports 2-6 legs")
    im = _canvas()
    _head(im, "PRO TIP — BUILDER" if kind == "builder" else "PRO TIP — LOTTERY")
    top = 290
    if len(teams) == 2:
        _teams(im, teams, 400, 150)
        _when(im, subtitle, 560)
        top = 650
    n = len(rows)
    total = re.search(r"\b(Quote|Berechnet|FORMEL-QA)\s+(\d+(?:[.,]\d+)?)", str(footer or ""), re.I)
    bottom = 1190 if total else 1250
    rh = min(130, (bottom - top) // n)
    for i, r in enumerate(rows):
        y = top + i * rh
        _panel(im, (40, y, 1040, y + rh - 12), CYAN, 20)
        _cutout(im, r.get("photo"), (50, y + 6, 50 + rh - 24, y + rh - 18))
        dd = ImageDraw.Draw(im)
        x = 50 + rh
        _text(dd, (x, y + (rh - 12) // 2 - 22), str(_need(r, "name")), 540, 34, WHITE, "lm")
        _text(dd, (x, y + (rh - 12) // 2 + 20), str(_need(r, "label")), 540, 30, GOLD, "lm")
        _text(dd, (1015, y + (rh - 12) // 2 - 14), _odds(r.get("odds")), 220, 40, GOLD, "rm")
        w = _windows(r.get("form"))
        if w:
            _text(dd, (1015, y + (rh - 12) // 2 + 24), "  ".join(f"{a} {b}" for a, b in w), 300, 20, GREEN, "rm")
    if total:
        real = total.group(1).lower() == "quote"
        _panel(im, (40, 1200, 1040, 1280), GOLD, 20)
        dd = ImageDraw.Draw(im)
        _text(dd, (70, 1240), "GESAMTQUOTE" if real else "BERECHNET", 300, 30, WHITE, "lm")
        _text(dd, (1010, 1240), f"{float(total.group(2).replace(',', '.')):.2f}", 240, 48, GOLD, "rm")
        if not real:
            _text(dd, (540, 1240), "KEINE BOOKIE-QUOTE", 380, 24, CYAN)
    _foot(im, 1296, settlement)
    return _png(im)


def is_master_card(png):
    """None: not a master-size card. (True, reason) verified / (False, reason) rejected."""
    from prop_hunter_telegram_safe_zone import split_owner_margin
    try:
        with Image.open(io.BytesIO(png)) as sent:
            if sent.format != "PNG" or sent.width != W:
                return None
            if sent.height not in (H, H + max(112, round(H * 0.075))):
                return None
            try:
                body, _ = split_owner_margin(sent, (H,))
            except ValueError:
                return False, "master_telegram_margin_missing_or_modified"
    except (OSError, ValueError, SyntaxError):
        return None
    master = _canvas().convert("RGB")
    from PIL import ImageChops
    for box in ((0, 0, 170, 170), (0, 1404, W, H)):
        if ImageChops.difference(body.crop(box), master.crop(box)).getbbox() is not None:
            return False, "master_arena_or_nba_mark_altered"
    return True, "master_background_verified"
