#!/usr/bin/env python3
"""PROP HUNTER NHL premium master templates (design proposal, NOT production-wired).

Reuses the approved NBA premium layout engine (same panels, neon boxes, rows,
form/model/stake blocks) with an NHL identity: procedural player-free ice-rink
artwork, NHL market labels and an EMPTY league-logo slot. The authentic NHL
logo is never drawn or faked here; it must be supplied/validated at runtime
(see card_templates/OTHER_LEAGUES_PREMIUM_REQUIREMENTS.md).
"""
from __future__ import annotations
import importlib.util, json, re, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter
import cairosvg

HERE=Path(__file__).resolve().parent
NBA=HERE.parent/'nba_premium_v2'
spec=importlib.util.spec_from_file_location('nba_masters',NBA/'build_masters.py')
nba=importlib.util.module_from_spec(spec); sys.modules['nba_masters']=nba; spec.loader.exec_module(nba)
W,H=nba.W,nba.H

MARKETS={
 'single':'PRO TIP · SINGLE','shots_on_goal':'SHOTS ON GOAL','goals':'TORE',
 'anytime_goal':'ANYTIME GOALSCORER','assists':'ASSISTS','points':'POINTS (G+A)',
 'power_play_points':'POWERPLAY POINTS','saves':'GOALIE SAVES','blocked_shots':'BLOCKED SHOTS',
 'hits':'HITS','moneyline':'MONEYLINE','match_total':'MATCH TOTAL','puck_line':'PUCK LINE'}
FAMILIES={'ladder':'NHL LADDER','builder':'NHL PROP BUILDER','same_player':'SAME PLAYER BUILDER',
          'cross_game':'CROSS GAME BUILDER','combo':'NHL COMBO / MULTI','lottery':'NHL LOTTERY'}
nba.FAMILIES=FAMILIES

def make_ice(path):
    """Original player-free rink artwork: dark arena, spotlights, ice with lines."""
    im=Image.new('RGB',(W,H),(3,10,24)); d=ImageDraw.Draw(im)
    for y in range(H):                                   # arena gradient
        t=y/H; d.line([(0,y),(W,y)],fill=(int(4+10*t),int(12+34*t),int(30+70*t)))
    glow=Image.new('RGB',(W,H),(0,0,0)); g=ImageDraw.Draw(glow)
    for cx in (110,330,540,750,970):                      # arena light rig
        g.ellipse([cx-70,30,cx+70,150],fill=(120,190,255))
        g.polygon([(cx-40,110),(cx+40,110),(cx+330,900),(cx-330,900)],fill=(28,64,104))
    glow=glow.filter(ImageFilter.GaussianBlur(46)); im=Image.blend(im,Image.composite(glow,im,glow.convert('L')),.85)
    ice=Image.new('RGB',(W,H),(0,0,0)); i=ImageDraw.Draw(ice)   # ice surface, bottom third in perspective
    top=880
    for y in range(top,H):
        t=(y-top)/(H-top); c=int(120+90*t)
        i.line([(0,y),(W,y)],fill=(c-40,c-6,min(255,c+30)))
    i.line([(0,top),(W,top)],fill=(230,245,255),width=6)
    i.rectangle([0,top,W,top+10],fill=(190,215,240))
    i.line([(0,top+130),(W,top+130)],fill=(210,32,48),width=10)       # red goal/centre line
    i.line([(0,top+320),(W,top+320)],fill=(30,90,200),width=12)       # blue line
    i.ellipse([W//2-230,top+160,W//2+230,top+500],outline=(210,32,48),width=8)   # face-off circle
    i.ellipse([W//2-14,top+320,W//2+14,top+348],fill=(210,32,48))
    ice=ice.filter(ImageFilter.GaussianBlur(3))
    mask=Image.new('L',(W,H),0); ImageDraw.Draw(mask).rectangle([0,top,W,H],fill=255)
    mask=mask.filter(ImageFilter.GaussianBlur(10))
    im=Image.composite(Image.blend(im,ice,.9),im,mask)
    glare=Image.new('RGB',(W,H),(0,0,0)); ImageDraw.Draw(glare).ellipse([200,top+30,880,top+330],fill=(110,150,200))
    glare=glare.filter(ImageFilter.GaussianBlur(70)); im=Image.blend(im,Image.composite(glare,im,glare.convert('L')),.5)
    im.save(path,quality=90,optimize=True)

LOGO_RE=re.compile(r'<image [^>]*assets/nba_logo\.png"[^>]*/>')
def adapt(svg):
    svg=LOGO_RE.sub(nba.asset_slot('league_logo',64,44,64,108).replace('data-frameless="true"','data-frameless="true" data-required="official-league-logo"'),svg)
    svg=svg.replace('assets/arena.jpg','assets/ice_rink.jpg').replace('layer-01-arena-photo','layer-01-rink-photo')
    svg=svg.replace('NBA-SPIELERPROPS','NHL-SPIELERPROPS').replace('NBA','NHL').replace('>ARENA<','>HALLE<')
    return svg

def build():
    (HERE/'assets').mkdir(exist_ok=True)
    make_ice(HERE/'assets'/'ice_rink.jpg')
    templates={}
    for key,label in MARKETS.items():
        name=f'single_{key}'
        (HERE/f'{name}.svg').write_text(adapt(nba.single(label)),encoding='utf8')
        templates[name]={'family':'single','market':key,'legs':1,'file':f'{name}.svg'}
    for family in FAMILIES:
        for n in range(2,7):
            key=f'{family}_{n}'
            (HERE/f'{key}.svg').write_text(adapt(nba.multi(family,n)),encoding='utf8')
            templates[key]={'family':family,'legs':n,'file':f'{key}.svg'}
    manifest={'version':1,'league':'NHL','format':'layered_svg','resolution':[W,H],'production_gated':True,
              'template_count':len(templates),'templates':templates,
              'rules':{'logo':'league_logo slot is EMPTY; official NHL logo must be supplied and validated, never drawn',
                       'photos':'transparent PNG cutouts only','odds':'only bookmaker-verified; missing stays blank',
                       'settlement':'edit original Telegram message only','background':'original player-free rink artwork'}}
    (HERE/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return manifest

def previews():
    m=json.loads((HERE/'manifest.json').read_text()); out=HERE/'previews'; out.mkdir(exist_ok=True)
    img=Path(HERE/'assets'/'ice_rink.jpg').read_bytes()
    import base64
    for k in ('single_single','single_shots_on_goal','ladder_4','builder_4','combo_5','lottery_6','same_player_4','cross_game_5'):
        svg=(HERE/m['templates'][k]['file']).read_text().replace('assets/ice_rink.jpg','data:image/jpeg;base64,'+base64.b64encode(img).decode())
        cairosvg.svg2png(bytestring=svg.encode(),write_to=str(out/f'{k}.png'),output_width=W)
    return sorted(p.name for p in out.glob('*.png'))

if __name__=='__main__':
    n=build()['template_count']; print('built',n); print(previews())
