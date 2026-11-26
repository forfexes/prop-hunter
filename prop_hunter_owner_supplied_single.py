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
import hashlib, os, re
from PIL import Image, ImageDraw, ImageFont, ImageChops

BASE = Path(__file__).resolve().parent / 'card_templates' / 'owner_supplied'
SOURCE = BASE / 'single_blank_20261122.png'
EDITABLE = BASE / 'single_blank_editable_20261122.png'
FLOATING = BASE / 'single_blank_floating_20261123.png'
NO_SILHOUETTE = BASE / 'single_blank_no_silhouette_20261123.png'
NO_SILHOUETTE_PIXEL_SHA = 'f625b53b43ccfc3ddee80a568397d278724118624539417dab753ecfe516cd09'
RING_REGIONS = ((140, 64, 374, 145),)  # entire empty crest band, including verified original VS
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
    if not all(path.is_file() for path in (SOURCE, EDITABLE, FLOATING, NO_SILHOUETTE)):
        raise ValueError('Owner Single original, empty crests and NO-SILHOUETTE master mandatory')
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest()!=SOURCE_SHA256:
        raise ValueError('User-provided source original was modified')
    with Image.open(SOURCE) as source, Image.open(EDITABLE) as editable, \
         Image.open(FLOATING) as floating, Image.open(NO_SILHOUETTE) as blank:
        if any(im.size!=(512,512) for im in (source,editable,floating,blank)):
            raise ValueError('Source size changed; do not scale to another design')
        # The new static plate is a genuine source-derived master, not a
        # screenshot repaint at Telegram render time. Only owner-gold
        # circle slots may differ from the already verified empty plate.
        from PIL import ImageOps
        base=editable.convert('RGB')
        plate=floating.convert('RGB')
        difference=ImageChops.difference(base,plate)
        allowed=Image.new('L',(512,512),0)
        mask_draw=ImageDraw.Draw(allowed)
        for x0,y0,x1,y1 in RING_REGIONS:
            mask_draw.rectangle((x0,y0,x1-1,y1-1),fill=255)
        outside=Image.composite(difference,Image.new('RGB',(512,512)),
                                ImageOps.invert(allowed))
        if outside.getbbox() or not difference.getbbox():
            raise ValueError('Floating master alters original artwork outside old ring slots')
        clean = blank.convert('RGB')
        if hashlib.sha256(clean.tobytes()).hexdigest()!=NO_SILHOUETTE_PIXEL_SHA:
            raise ValueError('Owner master still contains a second, gold player silhouette')
        # Only the OLD athlete silhouette may differ from the ring-free source.
        changed=ImageChops.difference(plate,clean).getbbox()
        if not changed or not (0 <= changed[0] and 51 <= changed[1] and
                               changed[2] <= 160 and changed[3] <= 327):
            raise ValueError('No-silhouette master changed other source artwork')
        return blank.convert('RGBA').copy()


def _logo(im, entry, center):
    if not isinstance(entry,(tuple,list)) or len(entry)!=2:
        raise ValueError('Two genuine team names and logos required')
    name,picture=entry
    if not str(name or '').strip() or not isinstance(picture,Image.Image):
        raise ValueError('Authentic NBA club and emblem missing')
    # Real emblem inside the owner's ORIGINAL circle. Crop the transparent
    # source margin and align both axes; never paste a new ring/sticker.
    from prop_hunter_owner_clean_single import _place_authentic_crest
    _place_authentic_crest(im,picture,center,108,70)
    _write(ImageDraw.Draw(im),(center,154),name,94,11,WHITE)


def _portrait(im, photo, *, centered_qa=False):
    """Only real ALPHA-cutout athlete pixels; no ghost, hard body mask or halo."""
    if not isinstance(photo,Image.Image):
        raise ValueError('Actual transparent athlete cutout photo mandatory')
    img=photo.convert('RGBA')
    alpha=img.getchannel('A')
    if alpha.getextrema()[0]>45:
        raise ValueError('Player image must have genuinely transparent edges')
    visible=alpha.point(lambda a:255 if a>=32 else 0).getbbox()
    if not visible:
        raise ValueError('Player image contains no real visible portrait')
    img=img.crop(visible)
    if min(img.size)<24:
        raise ValueError('Player photo has insufficient visible detail')
    # Contain the ENTIRE head and both natural shoulders in a stadium slot.
    # A fixed polygon body silhouette used to clip off real hair/faces and
    # expose a second gold-edged fake athlete. That masking is prohibited.
    # Keep the real athlete BELOW the immutable NBA shield and gold header.
    # Never hide forehead pixels behind a protected owner masthead.
    # Keep both owner's exact protected background sizes; photo enlargement
    # is QA-only and is drawn below team crests. All real portrait pixels
    # remain unchanged except for scaling and soft bottom fading.
    if centered_qa:
        scale=min(211/img.height,195/img.width)
    else:
        scale=min(189/img.height,174/img.width)
    w,h=max(1,round(img.width*scale)),max(1,round(img.height*scale))
    img=img.resize((w,h),Image.Resampling.LANCZOS)
    layer=Image.new('RGBA',(512,512),(0,0,0,0))
    x=max(0,round((95 if centered_qa else 88)-w/2))
    y=(max(73,276-h) if centered_qa else 254-h)
    layer.alpha_composite(img,(x,y))
    # Only a short natural fade at the jersey hem, never over the face.
    fade=Image.new('L',(512,512),255)
    d=ImageDraw.Draw(fade)
    if centered_qa:
        for yy in range(243,289):
            opacity=round(255*max(0,(282-yy)/39))
            d.line((0,yy,511,yy),fill=opacity)
    else:
        for yy in range(215,255):
            opacity=round(255*max(0,(249-yy)/34))
            d.line((0,yy,511,yy),fill=opacity)
    layer.putalpha(ImageChops.multiply(layer.getchannel('A'),fade))
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
    raw=str(value or 'OFFEN').strip()
    state=aliases.get(raw.casefold(),raw.upper())
    if state not in ('OFFEN','GEWONNEN','VERLOREN','PUSH','VOID'):
        # Stored result summaries can be count-based (e.g. '1 gewonnen ·
        # 0 verloren · +0.74u'). Do not mistake a mixed or absent result for
        # a verified single win. Exactly ONE positive result is required.
        counted=re.findall(r'\b(\d+)\s+(gewonnen|verloren|offen|push|void)\b',
                           raw.casefold())
        values={}
        for number,kind in counted:
            values[kind]=values.get(kind,0)+int(number)
        if sum(values.values())!=1:
            raise ValueError('Single settlement count must identify exactly one actual result')
        state=next({'gewonnen':'GEWONNEN','verloren':'VERLOREN',
                    'offen':'OFFEN','push':'PUSH','void':'VOID'}[key]
                   for key,count in values.items() if count==1)
    return state, WHITE if state in ('OFFEN','PUSH','VOID') else GREEN if state=='GEWONNEN' else RED


def render(*, title, subtitle, teams, row, footer, settlement, centered_qa=None):
    """Return source-derived 1080px PNG; no Telegram message or estimate."""
    if title!='SINGLE':
        raise ValueError('Owner supplied source is approved for Singles only')
    if not isinstance(teams,(list,tuple)) or len(teams)!=2 or not isinstance(row,dict):
        raise ValueError('Exactly two NBA teams and one observed player required')
    im=_plate()
    # Direct QA callers retain preview behaviour. The production bridge pins
    # the owner-approved geometry on each published snapshot.
    if centered_qa is None:
        centered_qa=os.getenv('PH_NBA_SINGLE_CENTERED_PREVIEW','0')=='1'
    _portrait(im,row.get('photo'),centered_qa=centered_qa)
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
    if centered_qa:
        # Centre of the actual 512px original canvas, not the right-hand
        # column; no opaque backing or logo/font replacement.
        _write(d,(256,199),name,298,24,WHITE,italic=False)
    else:
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
    # Keep the longer GEWONNEN text separated from the baked owner label
    # AUSWERTUNG: – one baseline, no overlap, no runtime sticker.
    _write(d,(281,471),state,80,15,color,italic=True)
    _write(d,(453,502),'@prophunter',100,11,WHITE,italic=True)
    im=im.convert('RGB').resize((1080,1080),Image.Resampling.LANCZOS)
    out=BytesIO();im.save(out,format='PNG',optimize=True)
    return out.getvalue()