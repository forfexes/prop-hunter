"""Pixel-based editable compositor for the four owner-supplied PROP HUNTER cards.

Use the exact user-uploaded JPEG artwork from card_templates/originals as the
source. Do NOT use synthetic poster families or fabricated values. Existing
sample labels, players, odds and logos are covered before inserting real pick
content. The top PROP HUNTER branding, card outlines, venue and ornamental
graphics remain from the original artwork.

This is a static bitmap compositing workflow (no generative redesign).
"""
from __future__ import annotations

import io
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

MASTER = Path(__file__).resolve().parent / 'card_templates' / 'originals'
FAMILIES = ('single', 'ladder', 'builder', 'lottery')
CROP = {
    'single': (0, 390, 691, 1148),
    'ladder': (0, 336, 691, 1201),
    'builder': (0, 336, 691, 1203),
    'lottery': (0, 394, 691, 1147),
}
NAVY = (3, 15, 29, 250)
DARK = (5, 19, 37, 255)
GOLD = (255, 210, 88)
WHITE = (250, 249, 249)
GREEN = (65, 240, 148)
VIOLET = (205, 85, 255)
CYAN = (83, 219, 254)
RED = (252, 79, 108)
FONT_BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf'
FONT_REG = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'


def _font(size: int, bold: bool = True):
    path = FONT_BOLD if bold else FONT_REG
    try:
        return ImageFont.truetype(path, max(9, size))
    except OSError:
        return ImageFont.load_default()


def _text(d: ImageDraw.ImageDraw, xy, text, size=24, width=400,
          color=WHITE, anchor='lt', bold=True, stroke=0):
    value = str(text or '').strip()
    if not value:
        return
    n = size
    while n > 11 and d.textlength(value, font=_font(n, bold)) > width:
        n -= 1
    f = _font(n, bold)
    if d.textlength(value, font=f) > width:
        while value and d.textlength(value + '…', font=f) > width:
            value = value[:-1]
        value += '…'
    d.text(xy, value, font=f, fill=color, anchor=anchor,
           stroke_width=stroke, stroke_fill=(0, 0, 0) if stroke else None)


def _rect(im, xy, color=DARK, radius=7, outline=None, w=2):
    ImageDraw.Draw(im).rounded_rectangle(xy, radius=radius, fill=color,
                                         outline=outline, width=w)


def _clean_hero(im, box):
    """Obscure baked-in example player without touching the original masthead."""
    x0, y0, x1, y1 = box
    # Local midnight arena gradient keeps the untouched masthead and card frame.
    patch = Image.new('RGBA', (x1-x0, y1-y0), NAVY)
    p = ImageDraw.Draw(patch)
    for j in range(y1-y0):
        t = j / max(y1-y0, 1)
        p.line([(0, j), (x1-x0, j)], fill=(4+int(t*2), 13+int(t*8), 27+int(t*19), 255))
    im.paste(patch, (x0, y0))


def _portrait(im, person, rect, name=''):
    x0, y0, x1, y1 = rect
    _rect(im, (x0, y0, x1, y1), NAVY, 9, GOLD, 2)
    if person is None:
        d = ImageDraw.Draw(im)
        _text(d, ((x0+x1)//2, (y0+y1)//2), 'FOTO FEHLT', 15,
              x1-x0-16, color=GOLD, anchor='mm')
        return
    picture = person.copy().convert('RGBA')
    # ESPN headshots are often transparent silhouettes; retain their cutout.
    picture.thumbnail((x1-x0-7, y1-y0-7), Image.Resampling.LANCZOS)
    offset = (x0+(x1-x0-picture.width)//2, y1-4-picture.height)
    if picture.getextrema()[3][0] == 255:
        picture = ImageOps.fit(picture, (x1-x0-8, y1-y0-8), method=Image.Resampling.LANCZOS)
        offset = (x0+4, y0+4)
    im.alpha_composite(picture, offset)


def _team(im, team, center, y, size=64):
    if not team:
        return
    name, logo = team
    cx = center
    _rect(im, (cx-size//2-8, y-5, cx+size//2+8, y+size+39), NAVY, 8)
    if logo is not None:
        img = logo.convert('RGBA')
        img.thumbnail((size, size), Image.Resampling.LANCZOS)
        im.alpha_composite(img, (cx-img.width//2, y+(size-img.height)//2))
    d = ImageDraw.Draw(im)
    _text(d, (cx, y+size+9), name, 14, size+38, color=WHITE, anchor='mt')


def _row(im, xy, width, name, market, odds, form, result='', no=None,
         photo=None, color=CYAN):
    x, y = xy
    height = 49
    _rect(im, (x, y, x+width, y+height), (4, 18, 33, 255), 4, color, 1)
    shift = 0
    if photo is not None:
        _portrait(im, photo, (x+3, y+3, x+46, y+46), name)
        shift = 48
    d = ImageDraw.Draw(im)
    if no is not None:
        _text(d, (x+5+shift, y+3), f'{no}. STUFE', 15, 120, GOLD)
        _text(d, (x+5+shift, y+23), market, 19, width-154-shift, GOLD)
    else:
        _text(d, (x+5+shift, y+3), name, 17, width-143-shift)
        _text(d, (x+5+shift, y+23), market, 18, width-155-shift, GOLD)
    if odds:
        _text(d, (x+width-10, y+5), odds, 19, 90, GOLD, 'rt')
    if form:
        _text(d, (x+width-10, y+28), form, 12, 144, GREEN, 'rt')
    if result:
        status_col = RED if 'VERLOREN' in result.upper() else GREEN if 'GEWONNEN' in result.upper() else WHITE
        _text(d, (x+width-10, y+42), result, 10, 122, status_col, 'rb')


def _family(kind):
    v = str(kind or '').lower()
    if v in ('big','super','lottery'): return 'lottery'
    if v in ('betbuilder','builder','combo','kombi','cross','same_game'): return 'builder'
    if v in ('single','ladder'): return v
    raise ValueError(f'Unsupported card family: {kind}')


@lru_cache(maxsize=4)
def _source(family):
    path = MASTER / (family + '.jpg')
    if not path.is_file():
        raise FileNotFoundError(f'User original JPG not in repo: {path}')
    source = Image.open(path).convert('RGBA')
    if source.size != (691, 1536):
        raise ValueError(f'User original JPG is not 691x1536: {path}')
    return source.crop(CROP[family])


def _league_badge(im, sport_label):
    name = str(sport_label or 'NBA').upper()
    league = ('WNBA' if 'WNBA' in name else 'NHL' if 'NHL' in name else
              'NFL' if 'NFL' in name else 'MLB' if 'MLB' in name else
              'NCAAF' if 'NCAAF' in name else 'NCAAB' if 'NCAAB' in name else
              'EUROLEAGUE' if 'EUROLEAGUE' in name else 'NBA')
    if league == 'NBA':
        return  # Original NBA branding intentionally untouched.
    _rect(im, (12, 13, 103, 129 if league != 'WNBA' else 104), NAVY, 9, CYAN, 2)
    _text(ImageDraw.Draw(im), (57, 48), league, 24, 82, WHITE, 'mm')


def _header(im, family, sport_label, subtitle, teams):
    _league_badge(im, sport_label)
    if family == 'single':
        _rect(im, (227, 143, 349, 273), NAVY, 9)
        _rect(im, (400, 143, 514, 273), NAVY, 9)
        boxes = ((278, 155), (457, 155))
        _rect(im, (517, 142, 689, 263), NAVY, 8, CYAN, 1)
    elif family == 'ladder':
        _rect(im, (124, 152, 248, 281), NAVY, 8)
        _rect(im, (328, 152, 475, 281), NAVY, 8)
        boxes = ((183, 160), (400, 160))
        _rect(im, (490, 150, 687, 280), NAVY, 8, CYAN, 1)
    elif family == 'builder':
        _rect(im, (108, 411, 315, 481), NAVY, 7)
        _rect(im, (380, 411, 608, 481), NAVY, 7)
        boxes = ((177, 414), (430, 414))
        _rect(im, (158, 482, 543, 512), NAVY, 5, GOLD, 1)
    else:
        _rect(im, (203, 147, 317, 271), NAVY, 8)
        _rect(im, (388, 147, 490, 271), NAVY, 8)
        boxes = ((252, 151), (432, 151))
        _rect(im, (513, 109, 689, 251), NAVY, 8, VIOLET, 1)
    for i, item in enumerate(teams[:2]):
        _team(im, item, boxes[i][0], boxes[i][1], size=(41 if family == "builder" else 63))
    d = ImageDraw.Draw(im)
    if family == 'builder':
        _text(d, (348, 498), subtitle, 16, 353, WHITE, 'mm')
    elif family == 'single':
        _text(d, (602, 172), subtitle, 12, 143, WHITE, 'mt')
    elif family == 'ladder':
        _text(d, (584, 185), subtitle, 13, 180, WHITE, 'mt')
    else:
        _text(d, (600, 144), subtitle, 12, 155, WHITE, 'mt')


def _f(form):
    # Input is taken from verified L10/L15 features; never fabricate samples.
    return str(form or '').replace('   ', ' · ').replace('  ', ' ')


def _result(im, family, settlement):
    bottom = {'single':(335, 662, 470, 701),'ladder':(363, 766, 496, 817),
              'builder':(586, 735, 670, 780),'lottery':(380, 655, 504, 694)}[family]
    x0,y0,x1,y1 = bottom
    label = str(settlement or 'OFFEN')
    _rect(im, bottom, (6, 19, 31, 255), 3)
    red = 'verloren' in label.lower() or '−' in label or '-0' in label
    green = 'gewonnen' in label.lower() and not red
    _text(ImageDraw.Draw(im), ((x0+x1)//2, (y0+y1)//2), label,
          18 if len(label)<26 else 13, x1-x0-7,
          RED if red else GREEN if green else GOLD, 'mm')


def original_card(kind: str, title: str, subtitle: str, sport: str,
                  teams: list, rows: list, footer: str='', settlement: str='',
                  *, league_name: str='') -> bytes:
    """Render dynamic data onto the literal original source screenshot (no generated poster)."""
    family = _family(kind)
    if not rows:
        raise ValueError('No pick rows')
    if family == 'ladder':
        distinct = {str(r.get('name') or '').strip().casefold() for r in rows}
        if len(distinct) != 1 or not next(iter(distinct)):
            raise ValueError('Ladder must use exactly one real athlete, not a builder')
    im = _source(family).copy()
    # Source frame and decorative motifs remain pixel-identical outside the dynamic slots.
    _header(im, family, league_name or sport, subtitle, teams)
    d = ImageDraw.Draw(im)
    if family == 'single':
        item = rows[0]
        _clean_hero(im, (95, 83, 239, 458))
        _clean_hero(im, (0, 137, 100, 458))
        _portrait(im, item.get('photo'), (3, 139, 235, 457), item.get('name') or '')
        _rect(im, (250, 287, 556, 377), NAVY, 5)
        _text(d, (395, 301), item.get('name'), 29, 280, WHITE, 'mt')
        _text(d, (395, 339), title if title not in ('SINGLE','') else 'PRO TIP', 19, 275, GOLD, 'mt')
        _rect(im, (170, 378, 468, 439), (4, 44, 35, 255), 10, GREEN, 3)
        _text(d, (322, 407), item.get('label'), 30, 272, WHITE, 'mm')
        _rect(im, (475, 380, 614, 438), (65, 39, 5, 255), 10, GOLD, 2)
        _text(d, (545, 408), item.get('odds') or '—', 28, 125, GOLD, 'mm')
        _rect(im, (35, 499, 244, 600), NAVY, 4)
        form = _f(item.get('form'))
        for number, y in ((10, 516), (15, 550)):
            match = re.search(rf'\bL{number}\s*(\d+/\d+)', form, re.I)
            _text(d, (48, y), f'L{number}', 19, 56, WHITE)
            _text(d, (232, y), match.group(1) if match else '—', 19, 123, GREEN, 'rt')
        _text(d, (48, 582), 'FORM', 17, 78, WHITE)
        _rect(im, (402, 500, 506, 597), NAVY, 3)
        _text(d, (451, 537), '—', 26, 95, WHITE, 'mm')
        _rect(im, (526, 518, 666, 594), (17, 18, 24, 255), 5, GOLD, 2)
        _text(d, (594, 552), footer or '—', 20, 130, GOLD, 'mm')
    elif family == 'ladder':
        # Remove all THREE old athletes and badges, then draw ONE hero photograph.
        _clean_hero(im, (0, 270, 247, 621))
        _rect(im, (202, 352, 685, 615), NAVY, 6)
        _portrait(im, rows[0].get('photo'), (15, 300, 197, 606), rows[0].get('name') or '')
        _rect(im, (379, 290, 660, 343), NAVY, 5, CYAN, 2)
        _text(d, (515, 317), footer or 'LADDER', 22, 254, GOLD, 'mm')
        if len(rows) > 5:
            raise ValueError('Ladder has more than five rungs; cannot fit faithfully')
        ys = [355 + i * (max(50, 246 // len(rows))) for i in range(len(rows))]
        for index, (y, r) in enumerate(zip(ys, rows), 1):
            _row(im, (204, y), 480, r.get('name'), r.get('label'), r.get('odds'),
                 _f(r.get('form')), r.get('result'), no=index, color=CYAN)
        _rect(im, (53, 670, 290, 741), NAVY, 8, CYAN, 1)
        _text(d, (169, 704), '1 SPIELER · MEHRERE STUFEN', 16, 217, GOLD, 'mm')
        _rect(im, (321, 657, 670, 742), NAVY, 7, CYAN, 1)
        for i, row in enumerate(rows[:3]):
            _text(d, (341, 666+i*23), f'{i+1}. {row.get("label") or ""} {row.get("odds") or ""}', 14, 314, WHITE)
    elif family == 'builder':
        # Clear all three stale athlete portraits and all printed example info.
        _clean_hero(im, (0, 135, 691, 411))
        n = min(len(rows), 6)
        w = 681 // max(1, min(n,3))
        for i, r in enumerate(rows[:3]):
            x = 8 + i * w
            _portrait(im, r.get('photo'), (x+8, 116, x+w-8, 276), r.get('name') or '')
            _rect(im, (x+4, 281, x+w-5, 345), NAVY, 6, GOLD, 1)
            _text(d, (x+w//2, 291), r.get('name'), 17, w-17, WHITE, 'mt')
            _text(d, (x+w//2, 319), r.get('label'), 17, w-17, GOLD, 'mt')
            _rect(im, (x+4, 357, x+w-5, 408), NAVY, 4, CYAN, 1)
            _text(d, (x+w//2, 372), _f(r.get('form')) or '—', 15, w-17, GREEN, 'mt')
        _rect(im, (423, 527, 662, 580), (55, 35, 8, 255), 7, GOLD, 2)
        _text(d, (540, 549), footer or '—', 19, 228, GOLD, 'mm')
        _rect(im, (82, 590, 646, 710), NAVY, 5, CYAN, 1)
        for i, r in enumerate(rows[:6]):
            _text(d, (103, 597+i*18),
                  f'{i+1}. {r.get("name") or ""} · {r.get("label") or ""}',
                  15, 530, GOLD)
        _rect(im, (83, 735, 320, 779), NAVY, 5)
        _text(d, (195, 755), f'{len(rows)} LEGS', 18, 205, GREEN, 'mm')
    elif family == 'lottery':
        _clean_hero(im, (0, 83, 202, 287))
        _clean_hero(im, (0, 287, 93, 337))
        _portrait(im, rows[0].get('photo'), (6, 62, 197, 280), rows[0].get('name') or '')
        _rect(im, (462, 280, 654, 335), (50, 18, 70, 255), 6, VIOLET, 2)
        _text(d, (559, 305), footer or '—', 24, 182, GOLD, 'mm')
        _rect(im, (183, 282, 435, 326), (40, 15, 56, 255), 7, VIOLET, 2)
        _text(d, (311, 302), f'{len(rows)}-LEG LOTTERY', 22, 239, WHITE, 'mm')
        _rect(im, (46, 336, 646, 527), NAVY, 7, VIOLET, 2)
        n = min(len(rows), 9)
        rh = max(19, 180 // n)
        for i, row in enumerate(rows[:9]):
            yy = 338 + i * rh
            _text(d, (59, yy+4), f'{i+1}. {row.get("name") or ""} · {row.get("label") or ""}',
                  16, 420, GOLD)
            _text(d, (637, yy+4), (row.get('odds') or '') + '  ' + _f(row.get('form')),
                  12, 160, GREEN, 'rt')
        _rect(im, (39, 560, 363, 629), NAVY, 5)
        _text(d, (195, 592), f'{len(rows)} LEGS · HOHES RISIKO', 16, 309, VIOLET, 'mm')
        _rect(im, (417, 570, 610, 632), (34, 20, 44, 255), 7, VIOLET, 2)
        _text(d, (513, 601), footer or '—', 20, 180, GOLD, 'mm')
    _result(im, family, settlement)
    buf = io.BytesIO()
    im = im.convert('RGB')
    im = im.resize((1080, round(1080 * im.height / im.width)), Image.Resampling.LANCZOS)
    im.save(buf, 'PNG', optimize=True)
    return buf.getvalue()