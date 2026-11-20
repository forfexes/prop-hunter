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

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

MASTER = Path(__file__).resolve().parent / 'card_templates' / 'originals'
# Opt in only after a human-reviewed CLEAN source plate is committed.
# Never use the experimental inpainting previews as production artwork.
APPROVED_MASTER = Path(__file__).resolve().parent / 'card_templates' / 'approved'
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


def _blend_fill(im, box):
    """Flaeche mit dem Hintergrundverlauf der Vorlage fuellen (statt flachem Rechteck)."""
    import numpy as np
    x0, y0, x1, y1 = [int(v) for v in box]
    W, H = im.size
    x0, y0, x1, y1 = max(3, x0), max(3, y0), min(W - 4, x1), min(H - 4, y1)
    if x1 <= x0 or y1 <= y0:
        return
    a = np.asarray(im.convert('RGB'), dtype=np.float32)
    top = a[y0 - 3:y0 - 1, x0:x1].mean(axis=0)          # (w,3)
    bot = a[y1 + 1:y1 + 3, x0:x1].mean(axis=0)
    lef = a[y0:y1, x0 - 3:x0 - 1].mean(axis=1)          # (h,3)
    rig = a[y0:y1, x1 + 1:x1 + 3].mean(axis=1)
    h, w = y1 - y0, x1 - x0
    ty = np.linspace(0, 1, h)[:, None, None]
    tx = np.linspace(0, 1, w)[None, :, None]
    vert = top[None, :, :] * (1 - ty) + bot[None, :, :] * ty
    hor = lef[:, None, :] * (1 - tx) + rig[:, None, :] * tx
    patch = ((vert + hor) / 2.0).clip(0, 255).astype('uint8')
    im.paste(Image.fromarray(patch, 'RGB'), (x0, y0))


def _rect(im, xy, color=DARK, radius=7, outline=None, w=2):
    ImageDraw.Draw(im).rounded_rectangle(xy, radius=radius, fill=color,
                                         outline=outline, width=w)


def _erase_single_bridge(im):
    """Remove the baked-in Warriors bridge art from the owner-supplied single.

    It is a decorative watermark in the background, NOT a participating team.
    Fade the right arena section instead of replacing the owner's artwork.
    Dynamic odds boxes and lines are rendered AFTER this masking step.
    """
    x0, y0, x1, y1 = (523, 253, im.width, 485)
    layer = Image.new('RGBA', im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for y in range(y0, y1):
        p = (y - y0) / max(1, y1 - y0)
        color = (3 + int(2*p), 13 + int(7*p), 27 + int(9*p), 255)
        d.line((x0, y, x1, y), fill=color, width=1)
    # Feather the overlay at its upper and left boundary; full opacity on logo.
    mask = Image.new('L', im.size, 0)
    md = ImageDraw.Draw(mask)
    md.rectangle((x0 + 18, y0 + 14, x1 + 28, y1 - 14), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(15))
    im.paste(layer, (0, 0), mask)


def _hide_baked_single_head(im):
    """Replace the sample athlete's hair with actual clean stadium pixels.

    A stretched copy of the unobstructed RIGHT stadium sky is blended into
    the affected LEFT sky. No solid navy rectangle and no synthetic face.
    The NBA badge and gold header sit outside the masked region.
    """
    x0, y0, x1, y1 = 73, 60, 205, 165
    # Cover the sample hair down to the portrait border. Any lower seam
    # is subsequently hidden by the newly rendered portrait itself.
    donor = im.crop((536, 19, 682, 116)).resize(
        (x1-x0, y1-y0), Image.Resampling.LANCZOS)
    donor = donor.filter(ImageFilter.GaussianBlur(1.1))
    feather = Image.new('L', donor.size, 0)
    md = ImageDraw.Draw(feather)
    md.rectangle((7, 6, donor.width-4, donor.height), fill=255)
    feather = feather.filter(ImageFilter.GaussianBlur(4))
    im.paste(donor, (x0, y0), feather)


def _erase_redundant_match_box(im, family):
    """Replace the baked-in sample match-info panel with clean arena sky.

    Logos and matchup immediately to the left already identify both teams.
    A small kickoff label may be painted later ONLY with supplied timestamp.
    """
    if family == 'single':
        # The source section below this area was already cleaned of its
        # example bridge. Reuse that quiet dark arena texture, not a second
        # copy of roof floodlights.
        x0,y0,x1,y1 = 511, 136, 691, 287
        donor_box = (563, 298, 681, 423)
    elif family == 'ladder':
        # The original header text extends into x490..610. Only the far-right
        # skyline x616..690 is free of letters, preventing an 'R/S' ghost.
        x0,y0,x1,y1 = 488, 145, 691, 287
        donor_box = (615, 17, 688, 143)
    else:
        return
    donor = im.crop(donor_box).resize((x1-x0,y1-y0),Image.Resampling.LANCZOS)
    donor = donor.filter(ImageFilter.GaussianBlur(1))
    # Preserve natural header boundary with a soft left and top transition.
    mask = Image.new('L', donor.size, 255)
    mm = ImageDraw.Draw(mask)
    for x in range(9):
        alpha=int(255*x/9)
        mm.line((x,0,x,donor.height),fill=alpha)
    for y in range(9):
        alpha=int(255*y/9)
        mm.line((0,y,donor.width,y),fill=alpha)
    for y in range(10):
        alpha=int(255*y/10)
        mm.line((0,donor.height-1-y,donor.width,donor.height-1-y),fill=alpha)
    im.paste(donor, (x0,y0), mask)


def _verified_kickoff_label(subtitle):
    """Extract date/time already appended from a real commence_time field."""
    matched=re.search(r'\b(?:Mo|Di|Mi|Do|Fr|Sa|So)\s+\d{2}\.\d{2}\.(?:\s*·\s*\d{2}:\d{2})?',str(subtitle or ''))
    return matched.group(0) if matched else ''


def _paint_kickoff_label(im, family, subtitle):
    when=_verified_kickoff_label(subtitle)
    if not when:
        return
    is_time=bool(re.search(r'\d{2}:\d{2}',when))
    cx,cy=(603,194) if family=='single' else (589,208)
    d=ImageDraw.Draw(im)
    _text(d,(cx,cy-16),'SPIELBEGINN' if is_time else 'SPIELDATUM',
          14,166,GOLD,'mm')
    _text(d,(cx,cy+17),when,17,182,WHITE,'mm')


_DE_WD = {'Mo': 'Mo', 'Di': 'Di', 'Mi': 'Mi', 'Do': 'Do', 'Fr': 'Fr', 'Sa': 'Sa', 'So': 'So'}
_DE_MON = ('Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez')


def _panel_fields(subtitle):
    """(Datum, Uhrzeit, Venue1, Venue2) aus dem Untertitel; unbekannt -> ''."""
    import datetime as _dt
    text = str(subtitle or '')
    venue = ''
    if ' @@ ' in text:
        text, venue = text.split(' @@ ', 1)
    m = re.search(r'\b(Mo|Di|Mi|Do|Fr|Sa|So)\s+(\d{2})\.(\d{2})\.(?:\s*·\s*(\d{2}:\d{2}))?', text)
    date_s = time_s = ''
    if m:
        wd, dd, mm, hhmm = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
        today = _dt.date.today()
        year = today.year + (1 if mm < today.month - 6 else -1 if mm > today.month + 6 else 0)
        date_s = f'{wd}, {dd}. {_DE_MON[mm-1]} {year}'
        time_s = f'{hhmm} Uhr' if hhmm else ''
    v1 = v2 = ''
    if venue:
        name, _, city = venue.partition('|')
        v1 = name.strip()
        v2 = f'({city.strip()})' if city.strip() else ''
    return date_s, time_s, v1, v2


def _squeezed(im, x, cy, text, size, width, color=WHITE, bold=True):
    """Text linksbuendig, bei Platzmangel horizontal gestaucht (wie die schmale Vorlagenschrift)."""
    value = str(text or '').strip()
    if not value:
        return
    d0 = ImageDraw.Draw(im)
    n = size
    while True:
        f = _font(n, bold)
        w = int(d0.textlength(value, font=f))
        if w <= width / 0.72 or n <= 11:
            break
        n -= 1
    h = int(n * 1.5)
    layer = Image.new('RGBA', (max(w, 1) + 4, h), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((2, h // 2), value, font=f, fill=color, anchor='lm')
    if w > width:
        layer = layer.resize((max(1, int(layer.width * width / w)), h), Image.Resampling.LANCZOS)
    im.alpha_composite(layer, (x - 2, cy - h // 2))


def _paint_match_panel(im, family, subtitle):
    """Original-Vorlage behalten (Icons, Rahmen) und nur die Beispieltexte ersetzen."""
    date_s, time_s, v1, v2 = _panel_fields(subtitle)
    if family == 'single':
        x, xr = 574, 674
        rows = ((152, 178, 165), (186, 214, 200), (222, 260, None))
        gap_x = 568
    else:
        x, xr = 544, 668
        rows = ((162, 189, 176), (196, 224, 210), (231, 272, None))
        gap_x = 538
    d = ImageDraw.Draw(im)
    for (y0, y1, cy), kind in zip(rows, ('date', 'time', 'venue')):
        bg = im.getpixel((gap_x, (y0 + y1) // 2))
        d.rectangle((x - 2, y0, xr + 2, y1), fill=(bg[0], bg[1], bg[2], 255))
    w = xr - x
    _squeezed(im, x, rows[0][2], date_s or '—', 21, w)
    _squeezed(im, x, rows[1][2], time_s or '—', 21, w)
    mid = (rows[2][0] + rows[2][1]) // 2
    if v1:
        _squeezed(im, x, mid - 9, v1, 17, w)
        if v2:
            _squeezed(im, x, mid + 11, v2, 15, w, bold=False)
    else:
        _squeezed(im, x, mid, '—', 21, w)


def _erase_template_head_remnants(im, family):
    """Remove the sample athletes protruding above the new photo frames.

    Do not repaint the gold/purple header title, league badge, or crown. The
    original user artwork is retained everywhere outside these small masks.
    """
    if family == 'builder':
        # The original card has three example athletes (Tatum / Doncic /
        # Sabonis) whose hair begins above the new player-photo slots.
        zones = (
            (62, 91, 164, 141),     # left player hair, outside title banner
            (282, 107, 408, 143),   # centre sample hair over lower title border
            (526, 91, 631, 141),    # right hair, outside title banner
        )
    elif family == 'lottery':
        # Brunson's original face extends above the replacement hero frame.
        zones = ((65, 42, 200, 66),)
    else:
        return
    for x0, y0, x1, y1 in zones:
        x0, y0 = max(0,x0), max(0,y0)
        x1, y1 = min(im.width,x1), min(im.height,y1)
        if x1 <= x0 or y1 <= y0:
            continue
        patch = Image.new('RGBA', (x1-x0, y1-y0))
        pix = patch.load()
        for yy in range(y1-y0):
            for xx in range(x1-x0):
                # A muted dark-stadium colour instead of a bright/opaque block.
                t = yy/max(1,y1-y0-1)
                pix[xx,yy] = (4+int(t*2), 13+int(t*7),
                              28+int(t*11), 255)
        feather = Image.new('L', patch.size, 0)
        fp = feather.load()
        w,h = patch.size
        for yy in range(h):
            for xx in range(w):
                border=min(xx, yy, w-1-xx, h-1-yy)
                fp[xx,yy]=int(255*min(1,border/5))
        im.paste(patch,(x0,y0),feather)


def _fade_baked_lottery_arm(im):
    """Cover the sample Knicks player's shoulder outside the actual hero frame.

    A feathered side-to-stadium transition avoids the solid navy rectangle
    that used to sit across the original purple lottery banner.
    """
    x0,y0,x1,y1 = 0, 274, 135, 342
    patch = Image.new("RGBA",(x1-x0,y1-y0))
    pp=patch.load()
    mask=Image.new("L",(x1-x0,y1-y0),0)
    mp=mask.load()
    for y in range(y1-y0):
        t=y/max(1,y1-y0-1)
        for x in range(x1-x0):
            pp[x,y]=(7+int(3*t),13+int(5*t),29+int(13*t),255)
            left_fade=1 if x<77 else max(0,(x1-x)/58)
            upper_fade=min(1,y/8)
            lower_fade=min(1,(y1-y-1)/13)
            mp[x,y]=int(255*left_fade*upper_fade*lower_fade)
    im.paste(patch,(x0,y0),mask)


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


def _portrait(im, person, rect, name='', prominent=False):
    x0, y0, x1, y1 = rect
    _rect(im, (x0, y0, x1, y1), NAVY, 9, GOLD, 2)
    if person is None:
        d = ImageDraw.Draw(im)
        _text(d, ((x0+x1)//2, (y0+y1)//2), 'FOTO FEHLT', 15,
              x1-x0-16, color=GOLD, anchor='mm')
        return
    picture = person.copy().convert('RGBA')
    # Trim transparent padding from published headshots before sizing the hero.
    alpha_box = picture.getchannel('A').getbbox()
    if alpha_box and alpha_box != (0, 0, picture.width, picture.height):
        picture = picture.crop(alpha_box)
    if prominent and picture.getextrema()[3][0] < 255:
        # Transparent portrait cutouts are often much shorter than the frame.
        # Enlarge proportionally, cropping only side/shoulder overflow.
        target_w, target_h = x1-x0-8, y1-y0-8
        scale = max(target_h*0.88/max(1,picture.height),
                    target_w*0.88/max(1,picture.width))
        nw, nh = max(1,round(picture.width*scale)), max(1,round(picture.height*scale))
        picture = picture.resize((nw,nh), Image.Resampling.LANCZOS)
        tile = Image.new('RGBA',(target_w,target_h),(0,0,0,0))
        tile.paste(picture,((target_w-nw)//2,target_h-nh),picture.getchannel('A'))
        im.alpha_composite(tile,(x0+4,y0+4))
        return
    picture.thumbnail((x1-x0-7, y1-y0-7), Image.Resampling.LANCZOS)
    offset = (x0+(x1-x0-picture.width)//2, y1-4-picture.height)
    if picture.getextrema()[3][0] == 255:
        picture = ImageOps.fit(picture, (x1-x0-8, y1-y0-8), method=Image.Resampling.LANCZOS)
        offset = (x0+4, y0+4)
    im.alpha_composite(picture, offset)


def _single_clean_master():
    """The approved, sample-free user artwork. Absent until visual QA passes."""
    return APPROVED_MASTER / 'single.png'


def _background_portrait(im, person, rect):
    """Composite an alpha-cutout athlete into the arena WITHOUT a photo frame.

    Unlike _portrait(), this never draws a box or a border. The cutout's right
    and bottom edges fade into the original stadium background. An opaque JPEG
    is deliberately rejected: without an alpha cutout it would leave another
    visible rectangular block. Return True only when a real cutout was drawn.
    """
    if person is None:
        return False
    picture = person.copy().convert('RGBA')
    a = picture.getchannel('A')
    if a.getextrema()[0] >= 255:
        return False
    bbox = a.getbbox()
    if not bbox:
        return False
    picture = picture.crop(bbox)
    x0, y0, x1, y1 = [int(v) for v in rect]
    w, h = x1-x0, y1-y0
    if w < 20 or h < 20:
        return False
    # Preserve the entire face/torso silhouette, cropping only at the edges
    # of the left stadium zone. The player is anchored to the lower edge.
    scale = max((h * 0.98) / picture.height, (w * 0.94) / picture.width)
    nw = max(1, round(picture.width * scale))
    nh = max(1, round(picture.height * scale))
    picture = picture.resize((nw, nh), Image.Resampling.LANCZOS)
    tile = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    tile.paste(picture, ((w-nw)//2, h-nh))
    # Fade the cutout at the right and bottom into the arena; never mask
    # the head with a rectangular navy patch.
    fade = Image.new('L', (w, h), 255)
    fd = ImageDraw.Draw(fade)
    edge_w = min(42, w//4)
    for xx in range(w-edge_w, w):
        alpha = round(255 * (w-1-xx) / max(1,edge_w-1))
        fd.line((xx,0,xx,h-1), fill=alpha)
    edge_h = min(45, h//5)
    for yy in range(h-edge_h, h):
        alpha = round(255 * (h-1-yy) / max(1,edge_h-1))
        # Multiplicative fade so corners are feathered in both directions.
        row = Image.new('L',(w,1),alpha)
        row = ImageChops.multiply(fade.crop((0,yy,w,yy+1)),row)
        fade.paste(row,(0,yy))
    tile.putalpha(ImageChops.multiply(tile.getchannel('A'),fade))
    im.alpha_composite(tile, (x0, y0))
    return True


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
    # Short team nicknames fit the original logo frame without ellipsis.
    compact = str(name or '').strip()
    _parts = compact.split(' ', 1)
    if len(_parts) == 2 and _parts[0].isupper() and 2 <= len(_parts[0]) <= 4:
        compact = _parts[1]
    if len(compact) > 13:
        compact = compact.rsplit(' ', 1)[-1]
    _text(d, (cx, y+size+9), compact, 13, size+60, color=WHITE, anchor='mt')


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
    if form and result:
        # Zeile ist nur 49 px hoch: Form kurz (n steckt schon in "hits/n") + Ergebnis darunter.
        form = str(form).replace(' verfügbare Spiele', '').replace(' verfuegbare Spiele', '')
        _text(d, (x+width-10, y+24), form, 11, 144, GREEN, 'rt')
        status_col = RED if 'VERLOREN' in result.upper() else GREEN if 'GEWONNEN' in result.upper() else WHITE
        _text(d, (x+width-10, y+46), result, 10, 150, status_col, 'rb')
    elif form:
        _text(d, (x+width-10, y+28), form, 12, 144, GREEN, 'rt')
    elif result:
        status_col = RED if 'VERLOREN' in result.upper() else GREEN if 'GEWONNEN' in result.upper() else WHITE
        _text(d, (x+width-10, y+42), result, 10, 150, status_col, 'rb')


def _family(kind):
    v = str(kind or '').lower()
    if v in ('big','super','lottery'): return 'lottery'
    if v in ('betbuilder','builder','combo','kombi','kombi2','kombi3','cross','same_game'): return 'builder'
    if v in ('single','ladder'): return v
    raise ValueError(f'Unsupported card family: {kind}')


@lru_cache(maxsize=4)
def _source(family):
    approved = APPROVED_MASTER / (family + '.png')
    if family in FAMILIES and approved.is_file():
        # An explicitly approved owner-derived, sample-free master. Do not
        # substitute a generated screenshot or a raw prefilled screenshot.
        with Image.open(approved) as art:
            source = art.convert('RGBA')
            if source.size != (691, CROP[family][3] - CROP[family][1]):
                raise ValueError('Approved clean owner plate has incorrect dimensions')
            return source
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
        # The redundant right-hand Home/Away box is erased below.
    elif family == 'ladder':
        _rect(im, (124, 152, 248, 281), NAVY, 8)
        _rect(im, (328, 152, 475, 281), NAVY, 8)
        boxes = ((183, 160), (400, 160))
        # The redundant right-hand Home/Away box is erased below.
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
    # Eliminate duplicated team names in the right field.
    # Match names/logos stay next to VS. Only an evidence-backed kickoff appears.
    if family in ('single','ladder'):
        _paint_match_panel(im, family, subtitle)
    else:
        d = ImageDraw.Draw(im)
        if family == 'builder':
            _text(d, (348, 498), subtitle, 16, 353, WHITE, 'mm')
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
    _blend_fill(im, bottom)
    red = 'verloren' in label.lower() or '−' in label or '-0' in label
    green = 'gewonnen' in label.lower() and not red
    if red or green:
        # Sanduhr der Vorlage ueberdecken und Haken/Kreuz zeichnen.
        cx, cy = x0 - 20, (y0 + y1) // 2
        bg = im.getpixel((max(0, cx - 24), cy))
        dd = ImageDraw.Draw(im)
        dd.ellipse((cx-22, cy-25, cx+22, cy+19), fill=(bg[0], bg[1], bg[2], 255))
        col = RED if red else GREEN
        if green:
            dd.line([(cx-9, cy), (cx-3, cy+7), (cx+10, cy-8)], fill=col, width=5, joint='curve')
        else:
            dd.line([(cx-8, cy-8), (cx+8, cy+8)], fill=col, width=5)
            dd.line([(cx-8, cy+8), (cx+8, cy-8)], fill=col, width=5)
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
        if len(rows) > 5:
            raise ValueError('Ladder has more than five rungs')
    if family == 'builder' and len(rows) > 6:
        raise ValueError('Builder has more than six legs; cannot silently hide picks')
    if family == 'lottery' and len(rows) > 9:
        raise ValueError('Lottery has more than nine legs; cannot silently hide picks')
    if family in ('builder', 'lottery'):
        subtitle = str(subtitle or '').split(' @@ ')[0]
    approved_single = family == 'single' and _single_clean_master().is_file()
    im = _source(family).copy()
    if family in ('builder','lottery'):
        _erase_template_head_remnants(im, family)
    # The Golden State bridge in the SINGLE screenshot is misleading for other
    # matchups; remove it BEFORE painting player, teams, odds and model data.
    if family == 'single' and not approved_single:
        _erase_single_bridge(im)
    # Source frame and decorative motifs remain pixel-identical outside the dynamic slots.
    _header(im, family, league_name or sport, subtitle, teams)
    d = ImageDraw.Draw(im)
    if family == 'single':
        item = rows[0]
        if approved_single:
            # Approved look: the athlete is an independent, frameless cutout
            # on the stadium layer. No dark box and no golden photo border.
            cutout = _background_portrait(im, item.get('photo'), (0, 131, 246, 518))
            if item.get('photo') is not None and not cutout:
                raise ValueError('Borderless portrait requires a real transparent player cutout')
        else:
            # Legacy JPG contains an embedded example player. Keep the
            # previous safe renderer until a CLEAN plate is approved.
            _hide_baked_single_head(im)
            _clean_hero(im, (95, 140, 239, 458))
            _clean_hero(im, (0, 137, 100, 458))
            _portrait(im, item.get('photo'), (3, 139, 235, 457),
                      item.get('name') or '', prominent=True)
        _blend_fill(im, (250, 287, 556, 377))
        _text(d, (395, 301), item.get('name'), 29, 280, WHITE, 'mt')
        _text(d, (395, 339), title if title not in ('SINGLE','') else 'PRO TIP', 19, 275, GOLD, 'mt')
        _rect(im, (170, 378, 468, 439), (4, 44, 35, 255), 10, GREEN, 3)
        _text(d, (322, 407), item.get('label'), 30, 272, WHITE, 'mm')
        _rect(im, (475, 380, 614, 438), (65, 39, 5, 255), 10, GOLD, 2)
        _text(d, (545, 408), item.get('odds') or '—', 28, 125, GOLD, 'mm')
        # Hide baked-in 'FORM & STATS' heading, keep the original icon/frame.
        _rect(im, (71, 461, 245, 499), NAVY, 4)
        _text(ImageDraw.Draw(im), (78, 471), 'LETZTE SPIELE', 17, 158, WHITE)
        _rect(im, (35, 499, 244, 600), NAVY, 4)
        form = _f(item.get('form'))
        # Only real observed windows: no placeholder "FORM" row or invented sample.
        for number, y in ((5, 516), (10, 550), (15, 582)):
            match = re.search(rf'\bL{number}\s*(\d+/\d+)', form, re.I)
            _text(d, (48, y), f'L{number}', 19, 56, WHITE)
            _text(d, (232, y), match.group(1) if match else '—', 19, 123,
                  GREEN if match else GOLD, 'rt')
        # Display only original published metrics; unknown values stay unknown.
        _rect(im, (267, 498, 507, 598), NAVY, 3)
        model = item.get('model') or {}
        metrics = (
            ('PROB', str(model['prob']) + '%' if model.get('prob') else '—'),
            ('EDGE', str(model['edge']) + '%' if model.get('edge') else '—'),
            ('CONF', str(model['confidence']) if model.get('confidence') else '—'),
        )
        for j, (metric_name, metric_value) in enumerate(metrics):
            yy = 512 + 28*j
            _text(d, (281, yy), metric_name, 14, 80, WHITE)
            _text(d, (493, yy), metric_value, 16, 118,
                  GREEN if metric_value != '—' else GOLD, 'rt')
        _rect(im, (526, 518, 666, 594), (17, 18, 24, 255), 5, GOLD, 2)
        # The narrow stake box cannot hold a combined odds+stake sentence.
        stake = re.search(r'Einsatz\s+([\d.,]+u)', str(footer), re.I)
        _text(d, (594, 552), stake.group(1) if stake else '—', 22, 130, GOLD, 'mm')
    elif family == 'ladder':
        # Remove all THREE old athletes and badges, then draw ONE hero photograph.
        _clean_hero(im, (0, 270, 247, 621))
        _rect(im, (202, 352, 685, 615), NAVY, 6)
        _portrait(im, rows[0].get('photo'), (15, 300, 197, 606), rows[0].get('name') or '')
        # The owner JPEG has an old white 'LADDERS' legend behind this row.
        # Fully erase it before adding the clean dynamic stage heading.
        _rect(im, (246, 286, 383, 347), NAVY, 5)
        _text(ImageDraw.Draw(im), (313, 315), 'STUFEN', 22, 127, WHITE, 'mm')
        _rect(im, (379, 290, 660, 343), NAVY, 5, CYAN, 2)
        _text(d, (515, 317), footer or 'LADDER', 22, 254, GOLD, 'mm')
        # Keep every rung above the fixed footer (starts at y=615).
        # Center short ladders and compress five rungs without overlap.
        gap = 1 if len(rows) == 5 else 6
        occupied = 49*len(rows) + gap*(len(rows)-1)
        first = 352 + max(0,(254-occupied)//2)
        ys = [first + i*(49+gap) for i in range(len(rows))]
        for index, (y, r) in enumerate(zip(ys, rows), 1):
            _row(im, (204, y), 480, r.get('name'), r.get('label'), r.get('odds'),
                 _f(r.get('form')), r.get('result'), no=index, color=CYAN)
        _rect(im, (53, 670, 290, 741), NAVY, 8, CYAN, 1)
        _text(d, (169, 704), '1 SPIELER · MEHRERE STUFEN', 16, 217, GOLD, 'mm')
        # Hide the baked-in '(3-LEG)' label: the actual ladder can have 2-5 rungs.
        _rect(im, (319, 615, 670, 656), NAVY, 7, CYAN, 1)
        _text(ImageDraw.Draw(im), (494, 635), f'LADDERS ({len(rows)} STUFEN)', 19, 335, WHITE, 'mm')
        _rect(im, (321, 657, 670, 742), NAVY, 7, CYAN, 1)
        for i, row in enumerate(rows):
            _text(d, (341, 661+i*16),
                  f'{i+1}. {row.get("label") or ""} {row.get("odds") or ""}',
                  12, 314, WHITE)
    elif family == 'builder':
        # Remove the stale three sample athletes and reconstruct ALL submitted
        # player slots, up to six. The owner original remains the background.
        _clean_hero(im, (0, 135, 691, 411))
        n = len(rows)
        columns = min(n, 3)
        w = 681 // max(1, columns)
        if n <= 3:
            for i, r in enumerate(rows):
                x = 8 + i*w
                _portrait(im, r.get('photo'), (x+8, 116, x+w-8, 276), r.get('name') or '')
                _rect(im, (x+4, 281, x+w-5, 345), NAVY, 6, GOLD, 1)
                _text(d, (x+w//2, 291), r.get('name'), 17, w-17, WHITE, 'mt')
                _text(d, (x+w//2, 319), r.get('label'), 17, w-17, GOLD, 'mt')
                _rect(im, (x+4, 357, x+w-5, 408), NAVY, 4, CYAN, 1)
                _text(d, (x+w//2, 372), _f(r.get('form')) or '—',
                      15, w-17, GREEN, 'mt')
        else:
            # Two rows of 2/3 real athlete portraits. Previously the fourth,
            # fifth and sixth legs existed only in tiny text at the bottom.
            for i, r in enumerate(rows):
                col, rowno = i%3, i//3
                x = 8 + col*w
                py0, py1 = (123, 235) if rowno == 0 else (272, 363)
                label_y0, label_y1 = (236, 269) if rowno == 0 else (364, 409)
                _portrait(im, r.get('photo'),
                          (x+7, py0, x+w-8, py1), r.get('name') or '')
                _rect(im, (x+4,label_y0,x+w-5,label_y1), NAVY, 5, GOLD, 1)
                _text(d, (x+w//2, label_y0+3), r.get('name'),
                      14, w-15, WHITE, 'mt')
                _text(d, (x+w//2, label_y0+19),
                      r.get('label'), 13, w-16, GOLD, 'mt')
        # The original artwork says "3-LEG BUILDER" permanently. Redraw the
        # number with the ACTUAL submitted leg count.
        _rect(im, (82, 523, 419, 584), NAVY, 6, CYAN, 1)
        _text(d, (252, 553), f'{n}-LEG BUILDER', 23, 315, WHITE, 'mm')
        _rect(im, (423, 527, 662, 580), (55, 35, 8, 255), 7, GOLD, 2)
        _text(d, (540, 549), footer or '—', 19, 228, GOLD, 'mm')
        # Example player/team icon protrudes just above the list border.
        _rect(im, (82, 579, 150, 597), NAVY, 3)
        _rect(im, (82, 590, 646, 710), NAVY, 5, CYAN, 1)
        for i, r in enumerate(rows[:6]):
            _text(d, (103, 597+i*18),
                  f'{i+1}. {r.get("name") or ""} · {r.get("label") or ""}',
                  15, 530, GOLD)
        # Cover the whole baked-in probability/EV digits, not just their
        # left side. The original was leaking green percentage glyphs.
        _rect(im, (78, 731, 338, 782), NAVY, 5)
        _text(d, (206, 755), f'{len(rows)} LEGS', 18, 236, GREEN, 'mm')
    elif family == 'lottery':
        _clean_hero(im, (0, 83, 202, 287))
        _fade_baked_lottery_arm(im)
        # Join the violet ticket artwork under the hero instead of exposing a
        # black rectangular patch where the original athlete's jersey was.
        ribbon=ImageDraw.Draw(im)
        ribbon.polygon(((0,285),(113,285),(77,336),(0,336)),
                       fill=(35,13,59,255))
        ribbon.line(((0,285),(113,285),(77,336),(0,336)),
                    fill=(148,62,197,255),width=2)
        _portrait(im, rows[0].get('photo'), (6, 62, 197, 280), rows[0].get('name') or '')
        _rect(im, (462, 280, 654, 335), (50, 18, 70, 255), 6, VIOLET, 2)
        total_quote=re.search(r'Quote\s*(@[\d.,]+)', str(footer), re.I)
        _text(d, (559, 305), total_quote.group(1) if total_quote else '—',
              23, 182, GOLD, 'mm')
        _rect(im, (183, 282, 435, 326), (40, 15, 56, 255), 7, VIOLET, 2)
        _text(d, (311, 302), f'{len(rows)}-LEG LOTTERY', 22, 239, WHITE, 'mm')
        _rect(im, (46, 336, 646, 527), NAVY, 7, VIOLET, 2)
        n = min(len(rows), 9)
        rh = max(19, 180 // n)
        for i, row in enumerate(rows):
            yy = 338 + i * rh
            shift = 0
            # The user's lottery original uses individual player portraits.
            # Keep miniature photos where rows are tall enough; nine-leg cards
            # stay text-first so neither names nor odds are hidden.
            if n <= 6 and row.get('photo') is not None:
                icon_size = min(40, rh-5)
                _portrait(im,row.get('photo'),
                          (55, yy+2, 55+icon_size, yy+2+icon_size),
                          row.get('name') or '')
                shift = icon_size + 7
            _text(d, (59+shift, yy+4),
                  f'{i+1}. {row.get("name") or ""} · {row.get("label") or ""}',
                  16, 420-shift, GOLD)
            # Never print a truncated "L5 ... L10 ... L15 ..." fragment.
            # The list is narrow, especially on nine-leg lottery posters.
            # Preserve the real observed per-leg bookmaker price here.
            _text(d, (637, yy+4), row.get('odds') or '—',
                  15, 116, GREEN, 'rt')
        _rect(im, (39, 560, 363, 629), NAVY, 5)
        _text(d, (195, 592), f'{len(rows)} LEGS · HOHES RISIKO', 16, 309, VIOLET, 'mm')
        _rect(im, (417, 570, 610, 632), (34, 20, 44, 255), 7, VIOLET, 2)
        stake = re.search(r'Einsatz\s+([\d.,]+u)', str(footer), re.I)
        _text(d, (513, 601), stake.group(1) if stake else '—',
              22, 176, GOLD, 'mm')
    _result(im, family, settlement)
    buf = io.BytesIO()
    im = im.convert('RGB')
    im = im.resize((1080, round(1080 * im.height / im.width)), Image.Resampling.LANCZOS)
    im.save(buf, 'PNG', optimize=True)
    return buf.getvalue()