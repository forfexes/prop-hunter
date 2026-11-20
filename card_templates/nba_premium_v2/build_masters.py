#!/usr/bin/env python3
"""Generate 52 real editable PROP-HUNTER NBA master templates.

The photographic arena is a separate original, player-free artwork.
Every changing item is a named SVG data-field or data-image-slot.
No overpainting of old card screenshots, no prefilled bookmaker prices.
"""
from __future__ import annotations
import base64, io, json, math, os, re, zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
from PIL import Image, ImageDraw, ImageFont
import cairosvg

HERE=Path(__file__).resolve().parent
W,H=1080,1440
GOLD='#FFD66B'; BLUE='#35C9FF'; GREEN='#2CFF8E'; WHITE='#F5F7FF'; MUTED='#A9C9DE'; DARK='#04101F'

MARKETS={
'single':'PRO TIP · SINGLE','points':'POINTS','rebounds':'REBOUNDS','assists':'ASSISTS',
 'threes':'3-POINTER','pra':'PTS + REB + AST','points_rebounds':'PTS + REB',
 'points_assists':'PTS + AST','rebounds_assists':'REB + AST','steals':'STEALS',
 'blocks':'BLOCKS','stocks':'STEALS + BLOCKS','double_double':'DOUBLE-DOUBLE',
 'triple_double':'TRIPLE-DOUBLE','turnovers':'TURNOVERS','fouls':'FOULS',
 'first_basket':'FIRST BASKET','team_total':'TEAM TOTAL','match_total':'MATCH TOTAL',
 'moneyline':'MONEYLINE','spread':'SPREAD'
}
FAMILIES={'ladder':'NBA LADDER','builder':'NBA PROP BUILDER','same_player':'SAME PLAYER BUILDER',
          'cross_game':'CROSS GAME BUILDER','combo':'NBA COMBO / MULTI','lottery':'NBA LOTTERY'}


def esc(v):
    return str(v).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;')

def rect(x,y,w,h,rad=20,fill='url(#panel)',stroke=BLUE,sw=2,opacity=1):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rad}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" opacity="{opacity}"/>'

def txt(x,y,s,size=28,color=WHITE,anchor='start',field=None,italic=False,weight=800):
    return (f'<text x="{x}" y="{y}" font-family="DejaVu Sans,Arial,sans-serif" font-size="{size}" '
            f'font-weight="{weight}" font-style="{"italic" if italic else "normal"}" '
            f'text-anchor="{anchor}" fill="{color}"'+(f' data-field="{field}"' if field else '')+
            f'>{esc(s)}</text>')

def dynamic(x,y,key,size=30,color=WHITE,anchor='start',italic=False):
    return txt(x,y,'',size,color,anchor,field=key,italic=italic)

def gold_line(x1,y1,x2,y2):
    return f'<path d="M{x1} {y1} L{x2} {y2}" stroke="{GOLD}" stroke-width="2" opacity=".7"/>'

def neon_box(x,y,w,h,color=BLUE,rad=20,fill='url(#panel)'):
    return (rect(x-2,y-2,w+4,h+4,rad+2,'none',color,8,.11)+
            rect(x,y,w,h,rad,fill,color,2.7)+
            f'<path d="M{x+20} {y+3} H{x+w-20}" stroke="white" stroke-opacity=".62" stroke-width="2"/>')

def asset_slot(key,x,y,w,h):
    return f'<g id="slot-{key}" data-image-slot="{key}" data-x="{x}" data-y="{y}" data-width="{w}" data-height="{h}" data-frameless="true"/>'

def svg_start():
    return f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 {W} {H}" width="{W}" height="{H}">
<title>PROP HUNTER NBA premium layered master</title>
<defs>
<linearGradient id="panel" x2="0" y2="1"><stop stop-color="#143B64" stop-opacity=".96"/><stop offset=".24" stop-color="#07172E" stop-opacity=".95"/><stop offset="1" stop-color="#020A17" stop-opacity=".98"/></linearGradient>
<linearGradient id="gold" x2=".2" y2="1"><stop stop-color="#FFF9CD"/><stop offset=".24" stop-color="#FFE585"/><stop offset=".53" stop-color="#E5A831"/><stop offset=".75" stop-color="#FFF0A6"/><stop offset="1" stop-color="#A86C14"/></linearGradient>
<linearGradient id="metal" x2="0" y2="1"><stop stop-color="#FFFFFF"/><stop offset=".36" stop-color="#F9FCFF"/><stop offset=".54" stop-color="#C5D3E3"/><stop offset=".77" stop-color="#FFFFFF"/><stop offset="1" stop-color="#65758A"/></linearGradient>
<linearGradient id="green" x2="0" y2="1"><stop stop-color="#114D37"/><stop offset=".4" stop-color="#031D15"/><stop offset="1" stop-color="#020F0B"/></linearGradient>
<linearGradient id="amber" x2="0" y2="1"><stop stop-color="#765012"/><stop offset=".4" stop-color="#2A1703"/><stop offset="1" stop-color="#080E16"/></linearGradient>
<linearGradient id="glass" x2="0" y2="1"><stop stop-color="#0D2C4B" stop-opacity=".35"/><stop offset="1" stop-color="#030C19" stop-opacity=".85"/></linearGradient>
</defs>
<g id="layer-01-arena-photo" data-static-background="true"><image x="0" y="0" width="1080" height="1440" preserveAspectRatio="xMidYMid slice" xlink:href="assets/arena.jpg"/></g>
<g id="layer-02-arena-vignette">{rect(0,0,W,H,0,'#000A18','none',0,.23)}
<path d="M0 1000 H1080 V1250 H0Z" fill="#001328" opacity=".27"/></g>
'''

def header(label,small='NBA'):
    return f'''<g id="layer-03-branding">
<path d="M498 64 L510 23 L540 45 L570 23 L582 64Z" fill="url(#gold)" stroke="#FFF0A0" stroke-width="3"/>
<circle cx="540" cy="105" r="58" stroke="#E9B53C" stroke-width="4" fill="none" opacity=".65"/>
{txt(540,136,'PROP-HUNTER',69,'#031020','middle',italic=True)}
<text x="540" y="130" font-family="DejaVu Sans,Arial,sans-serif" font-size="69" font-weight="900" font-style="italic" text-anchor="middle" fill="url(#metal)" stroke="#E1A12C" stroke-width="1.8" paint-order="stroke">PROP-HUNTER</text>
<path d="M330 147 H750" stroke="#F3C25E" stroke-width="3" opacity=".9"/>
{neon_box(38,38,115,121,GOLD,16)}{txt(95,96,small,34,WHITE,'middle')}{txt(95,124,'PROPS',18,GOLD,'middle')}
{neon_box(231,164,618,76,GOLD,16,'url(#amber)')}{txt(540,217,label,30 if len(label)>22 else 36,'url(#gold)','middle',italic=True)}
</g>'''

def crest_pair(y=275,mini=False):
    """No crest frame; home/away names are editable text directly below logos."""
    size=100 if mini else 125
    x1,x2=(397,645) if not mini else (401,617)
    mid=(x1+x2+size)//2
    return f'''<g id="layer-05-floating-team-crests">
{asset_slot('home_logo',x1,y,size,size)}
{asset_slot('away_logo',x2,y,size,size)}
{txt(580,y+size*.64,'VS',54 if not mini else 46,'url(#gold)','middle',italic=True)}
{dynamic(x1+size/2,y+size+38,'home_name',22,WHITE,'middle',True)}
{dynamic(x2+size/2,y+size+38,'away_name',22,WHITE,'middle',True)}
</g>'''

def match_info(x=837,y=305):
    return f'''<g id="layer-06-match-metadata">
{txt(x,y,'DATUM',18,GOLD)}{dynamic(x,y+36,'date',22)}{gold_line(x,y+48,1050,y+48)}
{txt(x,y+92,'UHRZEIT',18,GOLD)}{dynamic(x,y+129,'time',22)}{gold_line(x,y+141,1050,y+141)}
{txt(x,y+184,'ARENA',18,GOLD)}{dynamic(x,y+220,'venue',19)}
</g>'''

def settlement(y=1260):
    return f'''<g id="layer-12-settlement">
{neon_box(39,y,765,95,GOLD,12,'url(#amber)')}
{txt(66,y+60,'◎ AUSWERTUNG:',34,WHITE,italic=True)}
{dynamic(540,y+60,'settlement',32,GOLD,'middle',True)}
{txt(1038,y+134,'@prophunter',28,WHITE,'end',True)}
</g>'''

def stats(y=833,for_ladder=False):
    s=f'<g id="layer-10-last-games-model-stake">'
    for x,w,title in ((24,377,'LETZTE SPIELE'),(417,375,'MODELL'),(809,247,'EINSATZ')):
        s+=neon_box(x,y,w,300,BLUE,22)+rect(x+7,y+7,w-14,60,14,'#062C4B','none',0,.75)
        s+=txt(x+20,y+49,title,27,WHITE,italic=True)
    for i,key in enumerate(('l5','l10','l15')):
        yy=y+120+i*68
        s+=rect(45,yy-34,335,54,24,'#071A30','#8AAFD3',1.6,.8)
        s+=txt(72,yy,key.upper(),31,WHITE,italic=True)
        s+=dynamic(356,yy,key,31,GOLD,'end',True)
    for i,key in enumerate(('prob','edge','conf')):
        yy=y+120+i*68
        s+=rect(438,yy-34,336,54,24,'#071A30','#8AAFD3',1.6,.8)
        s+=txt(455,yy,key.upper(),27,WHITE,italic=True)
        s+=dynamic(757,yy,key,29,GOLD,'end',True)
    s+=neon_box(827,y+103,210,155,GOLD,20,'url(#amber)')
    s+=dynamic(932,y+207,'stake',62,GOLD,'middle',True)
    return s+'</g>'

def single(label):
    s=svg_start()+header(label)
    s+=f'<g id="layer-04-frameless-athlete">{asset_slot("player_photo",-45,180,408,700)}</g>'
    s+=crest_pair(286)+match_info(838,286)
    s+=f'<g id="layer-07-player-name">{dynamic(692,567,"player_name",48,WHITE,"middle",True)}</g>'
    s+=f'<g id="layer-08-bet-market">{neon_box(303,603,531,112,GREEN,22,"url(#green)")}'
    s+=dynamic(566,673,'market',43,WHITE,'middle',True)
    s+=neon_box(850,603,202,112,GOLD,20,'url(#amber)')+dynamic(951,674,'odds',43,GOLD,'middle',True)+'</g>'
    s+=stats(801)+settlement(1228)+'</svg>'
    return s

def leg_row(x,y,w,h,i,family):
    # All leg-specific elements are independent; no baked players or sample odds.
    is_ladder=family in ('ladder','same_player')
    c=GREEN if is_ladder else BLUE
    s=f'<g id="layer-leg-{i}">'+neon_box(x,y,w,h,c,14)
    s+=rect(x+12,y+14,85,h-28,10,'url(#gold)','none',0,1)
    s+=txt(x+55,y+h/2+10,f'{i}.',30,'#071226','middle',True)
    if not is_ladder and family in ('builder','cross_game'):
        s+=asset_slot(f'leg_{i}_photo',x+103,y+4,round(min(h*.86,92)),h-8)
        left=x+215
    else:
        left=x+118
    s+=dynamic(left,y+h*.45,f'leg_{i}_name' if not is_ladder else f'leg_{i}_line',26,WHITE)
    s+=dynamic(left,y+h*.78,f'leg_{i}_market',24,MUTED)
    s+=neon_box(x+w-186,y+h/2-32,166,64,GOLD,14,'url(#amber)')
    s+=dynamic(x+w-103,y+h/2+10,f'leg_{i}_odds',27,GOLD,'middle',True)
    s+='</g>'
    return s

def multi(family,n):
    s=svg_start()+header(f'{FAMILIES[family]} · {n} LEGS')
    same=family in ('ladder','same_player')
    if same:
        s+=f'<g id="layer-04-frameless-athlete">{asset_slot("player_photo",-45,175,405,805)}</g>'
        s+=crest_pair(273,mini=True)+match_info(845,276)
        s+=f'<g id="layer-07-player-name">{dynamic(690,539,"player_name",46,WHITE,"middle",True)}</g>'
        x,w,top,bottom=298,750,566,1102
    else:
        s+=crest_pair(267,mini=True)+match_info(845,267)
        x,w,top,bottom=34,1012,510,1099
    gap=12 if n>=5 else 16
    row_h=(bottom-top-gap*(n-1))/n
    s+='<g id="layer-08-legs">'
    for i in range(1,n+1):s+=leg_row(x,round(top+(i-1)*(row_h+gap)),w,round(row_h),i,family)
    s+='</g>'
    s+='<g id="layer-09-combination">'
    if family=='ladder':
        for j,key in enumerate(('l5','l10','l15','prob','stake')):
            xx=28+j*209
            s+=neon_box(xx,1124,194,97,BLUE if j<4 else GOLD,14)
            s+=txt(xx+17,1160,key.upper() if key!='prob' else 'MODELL',22,WHITE,italic=True)
            s+=dynamic(xx+176,1200,key,29,GOLD,'end',True)
    else:
        s+=neon_box(35,1124,675,97,GOLD,16,'url(#amber)')
        s+=txt(62,1186,'GESAMTQUOTE',32,WHITE,italic=True)+dynamic(679,1186,'total_odds',38,GOLD,'end',True)
        s+=neon_box(726,1124,320,97,BLUE,16)
        s+=txt(746,1186,'EINSATZ',28,WHITE,italic=True)+dynamic(1022,1186,'stake',34,GOLD,'end',True)
    s+='</g>'
    s+=settlement(1240)+'</svg>'
    return s


def build():
    (HERE/'assets').mkdir(exist_ok=True)
    src=Path('/mnt/data/a_highly_detailed_cinematic_photorealistic_indoo.png')
    if not src.exists() and not (HERE/'assets'/'arena.jpg').exists():
        raise FileNotFoundError('Original arena artwork must be supplied; do not substitute a screenshot with baked players')
    if src.exists():
        im=Image.open(src).convert('RGB').resize((W,H),Image.Resampling.LANCZOS)
        im.save(HERE/'assets'/'arena.jpg',quality=88,optimize=True,subsampling=0)
    templates={}
    for key,label in MARKETS.items():
        name=f'single_{key}'
        (HERE/f'{name}.svg').write_text(single(label),encoding='utf8')
        templates[name]={'family':'single','market':key,'legs':1,'file':f'{name}.svg'}
    (HERE/'longshot.svg').write_text(single('NBA LONGSHOT'),encoding='utf8')
    templates['longshot']={'family':'longshot','legs':1,'file':'longshot.svg'}
    for family in FAMILIES:
        for n in range(2,7):
            key=f'{family}_{n}'
            (HERE/f'{key}.svg').write_text(multi(family,n),encoding='utf8')
            templates[key]={'family':family,'legs':n,'file':f'{key}.svg'}
    manifest={'version':2,'format':'layered_svg','resolution':[W,H],'not_live':True,
              'template_count':len(templates),'templates':templates,
              'rules':{'photos':'transparent PNG cutouts only; no frames; independent layers',
                       'logos':'floating without frames, with dynamic team names beneath',
                       'ladder':'exactly one player portrait; 2-6 steps',
                       'same_player':'exactly one player portrait; 2-6 distinct prop legs',
                       'builder':'2-6 legs with independent photos and markets',
                       'odds':'only bookmaker-verified odds; no multiplication of independent legs',
                       'settlement':'edit original Telegram message only',
                       'background':'original player-free arena photo; never cover old example data',
                       'missing':'leave blank; never invent numbers'}}
    (HERE/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return manifest


def _embed_arena(svg):
    image=base64.b64encode((HERE/'assets'/'arena.jpg').read_bytes()).decode('ascii')
    return svg.replace('xlink:href="assets/arena.jpg"',f'xlink:href="data:image/jpeg;base64,{image}"')


def render_png(name,values=None,images=None):
    manifest=json.loads((HERE/'manifest.json').read_text())
    if name not in manifest['templates']:raise KeyError(name)
    root=ET.fromstring(_embed_arena((HERE/manifest['templates'][name]['file']).read_text()))
    for el in root.iter():
        key=el.get('data-field')
        if key is not None and values and key in values:
            el.text=str(values[key])
        slot=el.get('data-image-slot')
        if slot and images and slot in images:
            raw=images[slot]
            with Image.open(io.BytesIO(raw)) as im:
                if im.format!='PNG':raise ValueError(f'{slot} must be PNG')
                if (slot=='player_photo' or slot.endswith('_photo')) and im.convert('RGBA').getchannel('A').getextrema()[0]==255:
                    raise ValueError('Portrait must be a transparent cutout')
            sub=ET.SubElement(el,'{http://www.w3.org/2000/svg}image')
            sub.set('x',el.get('data-x'));sub.set('y',el.get('data-y'))
            sub.set('width',el.get('data-width'));sub.set('height',el.get('data-height'))
            sub.set('preserveAspectRatio','xMidYMax meet')
            sub.set('{http://www.w3.org/1999/xlink}href','data:image/png;base64,'+base64.b64encode(raw).decode('ascii'))
    return cairosvg.svg2png(bytestring=ET.tostring(root,encoding='utf-8'),output_width=W,output_height=H)


def qa_and_previews():
    manifest=json.loads((HERE/'manifest.json').read_text())
    assert len(manifest['templates'])==52
    for key,meta in manifest['templates'].items():
        root=ET.parse(HERE/meta['file']).getroot()
        fields={el.get('data-field') for el in root.iter() if el.get('data-field')}
        slots=[el.get('data-image-slot') for el in root.iter() if el.get('data-image-slot')]
        assert len(slots)==len(set(slots)),key
        assert {'settlement'}.issubset(fields),key
        assert not any('data:image' in str(el.attrib) for el in root.iter()),key
        assert 'home_logo' in slots and 'away_logo' in slots,key
        if meta['family'] in ('single','longshot','ladder','same_player'):
            assert slots.count('player_photo')==1,key
        if meta['family'] in ('ladder','same_player'):
            assert sum(s.endswith('_photo') for s in slots)==1,key
        if meta['family'] in ('builder','cross_game'):
            assert sum(s.endswith('_photo') for s in slots)==meta['legs'],key
        if meta['legs']>1:
            assert ('total_odds' in fields) == (meta['family']!='ladder'),key
            assert 'stake' in fields,key
            assert f'leg_{meta["legs"]}_market' in fields,key
    previews=HERE/'previews';previews.mkdir(exist_ok=True)
    for key in ('single_single','ladder_4','builder_4','builder_6','same_player_4','combo_5','lottery_6','longshot'):
        (previews/f'{key}.png').write_bytes(render_png(key))
    keys=['single_single','single_points','single_rebounds','single_assists','longshot',
          'ladder_2','ladder_4','ladder_6','builder_2','builder_4','builder_6',
          'same_player_4','cross_game_5','combo_5','lottery_6']
    cols=5;tw,th=250,334;pad=20;lab=38
    overview=Image.new('RGB',(cols*(tw+pad)+pad,3*(th+lab+pad)+pad),(3,10,23))
    draw=ImageDraw.Draw(overview)
    try:font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',16)
    except:font=ImageFont.load_default()
    for i,key in enumerate(keys):
        x=pad+(i%cols)*(tw+pad);y=pad+(i//cols)*(th+lab+pad)
        pic=Image.open(io.BytesIO(render_png(key))).convert('RGB').resize((tw,th),Image.Resampling.LANCZOS)
        overview.paste(pic,(x,y))
        draw.text((x+4,y+th+7),key.replace('_',' ').upper(),font=font,fill=(255,213,102))
    overview.save(previews/'collection.png',quality=94)
    (HERE/'README.md').write_text('''# PROP HUNTER — NBA Premium Mastervorlagen v2

52 echte, **datenfreie**, mehrschichtige SVG-Master im freigegebenen blau-goldenen Arena-Stil.

## Aufbau
- `assets/arena.jpg`: eigenständiger Basketballarena-Hintergrund **ohne** Spieler, Teamwappen, Quoten, Namen oder Statistiken.
- `single_*.svg` (21): Single-Märkte; `longshot.svg` (1).
- `ladder_2.svg` bis `ladder_6.svg` (5): **ein** freigestellter Spieler, mehrere Stufen.
- `same_player_2.svg` bis `_6.svg` (5): **ein** Spieler, 2–6 verschiedene Props.
- `builder_2.svg` bis `_6.svg` (5): 2–6 Spieler/Legs mit eigenen transparenten Fotoebenen.
- `cross_game_2.svg` bis `_6.svg` (5), `combo_2.svg` bis `_6.svg` (5), `lottery_2.svg` bis `_6.svg` (5).

Jedes dynamische Textfeld ist mit `data-field` markiert. Fotos/Wappen sind separate `data-image-slot`-Ebenen. **Keine** eingebrannten Namen, Fotos, Wappen, Quoten oder Statistiken; **keine** überklebten Beispielkarten. Wappen sind frei schwebend und Teamnamen stehen darunter. Spieler links ohne Rahmen. Spielername kleiner, ohne PRO-TIP-Kasten oder Trennlinie.

`previews/` enthält die gerenderten **leeren** Master, nicht reale Tipps. Für die Produktionsnutzung: verifizierte Team-/Spieler-/Quotendaten einsetzen, SVG zu PNG rendern, Telegram-Nachricht bei Settlement **bearbeiten**. Nicht ungeprüft live aktivieren.

`build_masters.py` erzeugt die 52 SVGs und die Prüf-Vorschauen aus dem vorhandenen Arena-Bild. `manifest.json` definiert die Familien und Feldbelegungen.
''',encoding='utf8')
    with zipfile.ZipFile('/mnt/data/PROP_HUNTER_NBA_Premium_Mastervorlagen_52.zip','w',zipfile.ZIP_DEFLATED,compresslevel=7) as z:
        for p in HERE.rglob('*'):
            if p.is_file() and p.name!='__pycache__' and 'preview_test' not in p.name:
                z.write(p,p.relative_to(HERE.parent))
    print('PASS 52/52; preview',previews/'collection.png', 'zip', '/mnt/data/PROP_HUNTER_NBA_Premium_Mastervorlagen_52.zip')

if __name__=='__main__':
    build();qa_and_previews()
