#!/usr/bin/env python3
"""Hero-style SINGLE masters (design 'C · Spielerfokus') for NHL, AHL, MLB, WNBA.

Large frameless player cut-out slot, smoky league-tinted background, big player
name, matchup with crest slots, market line and a large odds figure. Everything
that changes is a named data-field / data-image-slot; no player, logo or price is
baked in. Own neutral emblem only. NOT production-wired (design proposal).
"""
from __future__ import annotations
import base64, importlib.util, json, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter
import cairosvg

HERE=Path(__file__).resolve().parent
def _load(name,path):
    spec=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(spec); sys.modules[name]=m; spec.loader.exec_module(m); return m
league=_load('league_build',HERE/'build_masters.py'); nba=league.nba
W,H=1080,1440
TINT={'nhl':((10,40,80),(40,170,235)),'ahl':((50,16,22),(235,100,80)),'mlb':((8,40,26),(90,210,120)),'wnba':((52,28,10),(245,150,60))}

def smoke(lg,path):
    rng=np.random.default_rng(abs(hash(lg))%2**32 if False else {'nhl':1,'ahl':2,'mlb':3,'wnba':4}[lg])
    base=np.zeros((H,W),float)
    for sigma,amp in ((120,1.0),(55,.6),(22,.3)):
        n=Image.fromarray((rng.random((H//4,W//4))*255).astype('uint8')).resize((W,H),Image.BICUBIC).filter(ImageFilter.GaussianBlur(sigma))
        a=np.asarray(n,float)/255; base+=amp*(a-a.mean())
    base=(base-base.min())/(base.max()-base.min())
    dark,light=(np.array(c,float) for c in TINT[lg])
    img=dark[None,None,:]*(1-base[...,None])*.7+light[None,None,:]*base[...,None]*.55+np.array([3,8,18])[None,None,:]
    yy=np.linspace(0,1,H)[:,None,None]; img=img*(1-.55*np.clip((yy-.45)/.55,0,1))   # darken lower half for text
    vig=1-.45*np.clip(((np.linspace(-1,1,W)[None,:])**2+(np.linspace(-1,1,H)[:,None])**2)/2,0,1)
    out=np.clip(img*vig[...,None],0,255)
    # spotlight glow behind the athlete area + fine light scratches for an icy / textured look
    ys,xs=np.mgrid[0:H,0:W]; glow=np.exp(-(((xs-540)/420.)**2+((ys-560)/430.)**2)); out=out+glow[...,None]*(light[None,None,:]*.55)
    sc=Image.new('L',(W,H),0); from PIL import ImageDraw; d=ImageDraw.Draw(sc)
    for _ in range(140):
        x=int(rng.integers(0,W)); y=int(rng.integers(0,int(H*.8))); L=int(rng.integers(60,260)); a=float(rng.uniform(-.5,.5))
        d.line([(x,y),(x+L,y+int(L*a))],fill=int(rng.integers(40,120)),width=1)
    sc=np.asarray(sc.filter(ImageFilter.GaussianBlur(.8)),float)/255
    out=out+sc[...,None]*light[None,None,:]*.9
    Image.fromarray(np.clip(out,0,255).astype('uint8')).save(path,quality=90,optimize=True)

def hero(lg,cfg):
    acc=cfg['accent']; name=cfg['name']
    s=nba.svg_start().replace('PROP HUNTER NBA premium layered master',f'PROP HUNTER {name} hero single master')
    s=s.replace('assets/arena.jpg',f'../assets/{lg}_hero_bg.jpg')
    # remove arena vignette block, keep defs
    s=s.split('<g id="layer-02-arena-vignette">')[0]
    s+=f'<g id="layer-03-wordmark"><text x="540" y="112" font-family="DejaVu Sans,Arial,sans-serif" font-size="84" font-weight="900" font-style="italic" text-anchor="middle" fill="url(#metal)">PROP HUNTER</text></g>'
    s+=f'<g id="layer-03-pill">{nba.txt(540,178,name+" SINGLE",34,"#EAF6FF","middle",italic=True)}'
    s+=f'<path d="M150 170 H345" stroke="{acc}" stroke-width="4"/><path d="M735 170 H930" stroke="{acc}" stroke-width="4"/></g>'
    s+=f'<g id="layer-03-emblem" transform="translate(-22,-20) scale(.9)">{league.emblem(cfg["glyph"],acc)}</g>'
    s+=f'<g id="layer-04-frameless-athlete">{nba.asset_slot("player_photo",90,200,900,760)}</g>'
    s+=f'<g id="layer-07-player-name">{nba.dynamic(540,1010,"player_name",84,"#F5F9FF","middle",True,max_width=980)}</g>'
    s+=f'<path d="M80 1038 H1000" stroke="{acc}" stroke-width="3" opacity=".9"/>'
    s+=f'<g id="layer-05-matchup">{nba.asset_slot("home_logo",205,1052,96,96)}{nba.asset_slot("away_logo",779,1052,96,96)}'
    s+=f'{nba.dynamic(540,1112,"matchup",40,"#F5F9FF","middle",True,max_width=440)}</g>'
    s+=f'<path d="M80 1170 H1000" stroke="{acc}" stroke-width="3" opacity=".9"/>'
    s+=f'<g id="layer-08-bet-market">{nba.dynamic(540,1238,"market",58,"#F5F9FF","middle",True,max_width=980)}{nba.dynamic(540,1346,"odds",120,"#FFFFFF","middle",True,max_width=700)}</g>'
    s+='<g id="layer-10-form">'
    for x,lab,key in ((190,'L5','l5'),(540,'L10','l10'),(890,'L15','l15')):
        s+=nba.txt(x-30,1398,lab,26,acc,'end',italic=True)+nba.dynamic(x-16,1398,key,28,"#F5F9FF",'start',True,max_width=130)
    s+='</g>'
    s+=f'<g id="layer-12-settlement">{nba.txt(60,1428,"AUSWERTUNG:",22,"#A9C9DE",italic=True)}{nba.dynamic(262,1428,"settlement",24,"#FFD66B","start",True,max_width=560)}'
    s+=f'{nba.dynamic(620,1428,"stake",24,"#FFD66B","start",True,max_width=200)}{nba.txt(1030,1428,"@prophunter",24,"#F5F9FF","end",italic=True)}</g></svg>'
    return s

def build():
    out=HERE/'hero'; out.mkdir(exist_ok=True); man={}
    for lg,cfg in league.LEAGUES.items():
        smoke(lg,HERE/'assets'/f'{lg}_hero_bg.jpg'); (out/f'{lg}_single_hero.svg').write_text(hero(lg,cfg),encoding='utf8')
        man[lg]=f'hero/{lg}_single_hero.svg'
    (out/'manifest.json').write_text(json.dumps({'design':'C-Spielerfokus','files':man},indent=2)+'\n')
    return man

def render(lg,values=None):
    import re
    svg=(HERE/'hero'/f'{lg}_single_hero.svg').read_text().replace(f'../assets/{lg}_hero_bg.jpg','data:image/jpeg;base64,'+base64.b64encode((HERE/'assets'/f'{lg}_hero_bg.jpg').read_bytes()).decode())
    if values:
        for k,v in values.items():
            svg=re.sub(r'(data-field="%s"[^>]*>)(</text>)'%k,lambda m:m.group(1)+str(v).replace('&','&amp;')+m.group(2),svg)
    return cairosvg.svg2png(bytestring=svg.encode(),output_width=W)

if __name__=='__main__':
    print(build()); pv=HERE/'previews'; pv.mkdir(exist_ok=True)
    for lg in league.LEAGUES:
        (pv/f'hero_{lg}_leer.png').write_bytes(render(lg))
    (pv/'hero_nhl_beispieltext.png').write_bytes(render('nhl',{'player_name':'SPIELERNAME','matchup':'HEIM @ AUSWÄRTS','market':'ÜBER 2,5 SCHÜSSE','odds':'1,85','l5':'4/5','l10':'7/10','l15':'10/15','settlement':'OFFEN','stake':'1U'}))
    print('ok')
