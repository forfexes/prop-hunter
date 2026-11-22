"""PROP HUNTER NBA Single – owner-supplied 22.11.2026 blank master.

Coordinates refer to the exact 512×512 image supplied by the owner, not a
similarly styled substitute. Original untouched source remains versioned.
Only a ONE-TIME derived editable master removes the baked 'OFFEN' footer word.
No runtime rectangles, stickers, fills or screenshot text cover-ups.
The module is render-only; never posts to Telegram.
"""
from __future__ import annotations
from pathlib import Path
from io import BytesIO
from datetime import datetime
import hashlib, re
from PIL import Image, ImageDraw, ImageFont, ImageChops

BASE = Path(__file__).resolve().parent / 'card_templates' / 'owner_supplied'
SOURCE = BASE / 'single_blank_20261122.png'
EDITABLE = BASE / 'single_blank_editable_20261122.png'
SOURCE_SHA256 = '499ed837eb187b672c9a7781553eb9889c9fe37bb501aef3df61da1010019692'
WHITE=(248,251,255)
GOLD=(255,216,105)
GREEN=(111,249,153)
RED=(255,112,117)
FONT='/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf'
FONT_ITALIC='/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-BoldOblique.ttf'


def _font(sz, italic=False):
    try:
        return ImageFont.truetype(FONT_ITALIC if italic else FONT, sz)
    except OSError:
        return ImageFont.load_default()


def _write(draw, pos, value, max_px, size=17, color=WHITE, italic=False, anchor='mm'):
    value=str(value or '').strip()
    if not value:
        return
    if '\n' in value or len(value)>80:
        raise ValueError('Text is not single-line verified slot data')
    f=_font(size, italic)
    while size>8 and draw.textbbox((0,0),value,font=f,stroke_width=0)[2]>max_px:
        size-=1
        f=_font(size, italic)
    if draw.textbbox((0,0),value,font=f)[2]>max_px:
        raise ValueError('Long text exceeds owner source slot')
    draw.text(pos, value, anchor=anchor,fill=color,font=f,
              stroke_width=1,stroke_fill=(4,10,16))


def _plate():
    if not SOURCE.is_file() or not EDITABLE.is_file():
        raise ValueError('User-provided original and derived clean master missing')
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest()!=SOURCE_SHA256:
        raise ValueError('User-provided source original was modified')
    with Image.open(SOURCE) as source, Image.open(EDITABLE) as editable:
        if source.size!=(512,512) or editable.size!=(512,512):
            raise ValueError('Source size changed; do not scale to another design')
        return editable.convert('RGBA').copy()


def _logo(im, entry, center):
    if not isinstance(entry,(tuple,list)) or len(entry)!=2:
        raise ValueError('Two genuine team names and logos required')
    name,picture=entry
    if not str(name or '').strip() or not isinstance(picture,Image.Image):
        raise ValueError('Authentic NBA club and emblem missing')
    thumb=picture.convert('RGBA').copy()
    thumb.thumbnail((54,54),Image.Resampling.LANCZOS)
    x=int(center-thumb.width/2)
    im.alpha_composite(thumb,(x,81))
    _write(ImageDraw.Draw(im),(center,154),name,94,11,WHITE)


def _portrait(im, photo):
    if not isinstance(photo,Image.Image):
        raise ValueError('Actual transparent player photo mandatory')
    img=photo.convert('RGBA')
    if img.getchannel('A').getextrema()[0]>45:
        raise ValueError('Player photo has no transparent cutout')
    # Letterbox *inside* the source silhouette, preserving the owner's gold
    # outer outline, neckline and slot artwork without repainting it.
    img.thumbnail((153,216),Image.Resampling.LANCZOS)
    layer=Image.new('RGBA',(512,512),(0,0,0,0))
    start_x=17+int((138-img.width)/2)
    start_y=250-img.height
    layer.alpha_composite(img,(start_x,start_y))
    mask=Image.new('L',(512,512),0)
    m=ImageDraw.Draw(mask)
    m.polygon([(65,67),(97,64),(114,80),(124,105),(120,142),
               (130,170),(144,199),(148,223),(137,246),
               (22,247),(16,216),(29,177),(43,148),(46,111),(52,83)],fill=255)
    a=ImageChops.multiply(layer.getchannel('A'),mask)
    layer.putalpha(a)
    im.alpha_composite(layer)


def _label_parts(raw):
    v=' '.join(str(raw or '').split())
    if not v:
        raise ValueError('Observed selection label missing')
    m=re.fullmatch(r'(Over|Under)\s+(\d+(?:[.,]\d+)?)\s+(.+)',v,re.I)
    if m:
        market=m.group(3).strip().upper()
        selection=f'{m.group(1).upper()} {m.group(2)}'
        return market,selection
    # Exact selection text remains true even if the market cannot be parsed.
    # No guessed market names or line corrections.
    return '',v


def _get_time(subtitle):
    # Only the verified fixture kickoff from NBA owner bridge is accepted.
    m=re.search(r'\b(Mo|Di|Mi|Do|Fr|Sa|So)\s+(\d{2}\.\d{2}\.\d{4})\s*·\s*(\d{2}:\d{2})\b',str(subtitle or ''))
    if not m:
        raise ValueError('Verified NBA tipoff time missing')
    return m.group(1)+' '+m.group(2),m.group(3)


def _stat(form,n):
    m=re.search(r'\bL'+str(n)+r'\s+(\d+)/(\d+)\b',str(form or ''),re.I)
    if not m:
        return '—'
    a,b=map(int,m.groups())
    return f'{a}/{b}' if (0<=a<=b<=n and b>0) else '—'


def _status(value):
    aliases={'win':'GEWONNEN','won':'GEWONNEN','loss':'VERLOREN',
             'lost':'VERLOREN','open':'OFFEN','pending':'OFFEN',
             'push':'PUSH','void':'VOID'}
    state=aliases.get(str(value or 'OFFEN').strip().casefold(),str(value or 'OFFEN').strip().upper())
    if state not in ('OFFEN','GEWONNEN','VERLOREN','PUSH','VOID'):
        raise ValueError('Only verified single status may be inserted')
    return state, WHITE if state in ('OFFEN','PUSH','VOID') else GREEN if state=='GEWONNEN' else RED


def render(*, title, subtitle, teams, row, footer, settlement):
    """Return source-derived 1080px PNG; no Telegram message or estimate."""
    if title!='SINGLE':
        raise ValueError('Owner supplied source is approved for Singles only')
    if not isinstance(teams,(list,tuple)) or len(teams)!=2 or not isinstance(row,dict):
        raise ValueError('Exactly two NBA teams and one observed player required')
    im=_plate()
    _portrait(im,row.get('photo'))
    _logo(im,teams[0],191)
    _logo(im,teams[1],322)
    d=ImageDraw.Draw(im)
    date,clock=_get_time(subtitle)
    _write(d,(459,84),date,74,10,GOLD)
    _write(d,(457,115),clock+' Uhr',77,12)
    # Arena row has intentionally no value: neither league nor venue is
    # invented when the genuine location is not supplied by source data.
    name=str(row.get('name') or '').strip()
    if len(name.split())<2:
        raise ValueError('Verified full player name required')
    _write(d,(308,199),name,314,23,WHITE,italic=True)
    market,selection=_label_parts(row.get('label'))
    _write(d,(272,247),market,229,16,WHITE)
    _write(d,(218,287),selection,210,19,WHITE)
    quote=str(row.get('odds') or '').strip()
    if not re.fullmatch(r'@?\d{1,4}(?:[.,]\d{1,3})?',quote):
        raise ValueError('Real observed decimal bookmaker quote required')
    _write(d,(410,288),quote if quote.startswith('@') else '@'+quote,104,19,GOLD)
    for n,y in ((5,362),(10,389),(15,410)):
        _write(d,(48,y),'L'+str(n),44,13,WHITE)
        _write(d,(143,y),_stat(row.get('form'),n),65,13,GREEN)
    models=row.get('model') or {}
    for key,label,y in (('prob','PROB',363),('edge','EDGE',388),('confidence','CONF',410)):
        val=str(models.get(key) or '').strip()
        if val and key in ('prob','edge') and not val.endswith('%'):
            val+='%'
        _write(d,(222,y),label,50,12,WHITE)
        _write(d,(328,y),val or '—',60,12,GREEN if val else GOLD)
    stake=re.search(r'\bEinsatz\s+([\d.,]+u)\b',str(footer or ''),re.I)
    _write(d,(434,386),stake.group(1) if stake else '—',87,22,GOLD)
    state,color=_status(settlement)
    _write(d,(274,471),state,91,17,color,italic=True)
    _write(d,(453,502),'@prophunter',100,11,WHITE,italic=True)
    im=im.convert('RGB').resize((1080,1080),Image.Resampling.LANCZOS)
    out=BytesIO();im.save(out,format='PNG',optimize=True)
    return out.getvalue()