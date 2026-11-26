#!/usr/bin/env python3
"""PROP HUNTER league masters (NHL, AHL, MLB, WNBA) — design proposal, NOT production-wired.

Same layout engine as the approved NBA premium masters. Each league gets a
procedural player-free background and an OWN NEUTRAL emblem (generic puck /
baseball / basketball shield). No official league or team logo is drawn or
imitated; official logos/portraits are runtime image slots (home_logo,
away_logo, *_photo) that must be supplied and validated.
"""
from __future__ import annotations
import base64, importlib.util, json, re, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter
import cairosvg

HERE=Path(__file__).resolve().parent
NBA=HERE.parent/'nba_premium_v2'
spec=importlib.util.spec_from_file_location('nba_masters',NBA/'build_masters.py')
nba=importlib.util.module_from_spec(spec); sys.modules['nba_masters']=nba; spec.loader.exec_module(nba)
W,H=nba.W,nba.H

LEAGUES={
 'nhl':{'name':'NHL','venue':'HALLE','bg':'ice','accent':'#35C9FF','glyph':'puck','markets':{
   'single':'PRO TIP · SINGLE','shots_on_goal':'SHOTS ON GOAL','goals':'TORE','anytime_goal':'ANYTIME GOALSCORER',
   'assists':'ASSISTS','points':'POINTS (G+A)','power_play_points':'POWERPLAY POINTS','saves':'GOALIE SAVES',
   'blocked_shots':'BLOCKED SHOTS','hits':'HITS','moneyline':'MONEYLINE','match_total':'MATCH TOTAL','puck_line':'PUCK LINE'}},
 'ahl':{'name':'AHL','venue':'HALLE','bg':'ice_red','accent':'#FF6A5C','glyph':'puck','markets':{
   'single':'PRO TIP · SINGLE','shots_on_goal':'SHOTS ON GOAL','goals':'TORE','assists':'ASSISTS','points':'POINTS (G+A)',
   'saves':'GOALIE SAVES','moneyline':'MONEYLINE','match_total':'MATCH TOTAL'}},
 'mlb':{'name':'MLB','venue':'STADION','bg':'field','accent':'#7DFF8A','glyph':'ball','markets':{
   'single':'PRO TIP · SINGLE','hits':'HITS','home_runs':'HOME RUNS','strikeouts':'STRIKEOUTS','total_bases':'TOTAL BASES',
   'rbis':'RBIs','runs':'RUNS','moneyline':'MONEYLINE','run_line':'RUN LINE','match_total':'MATCH TOTAL'}},
 'wnba':{'name':'WNBA','venue':'ARENA','bg':'court','accent':'#FFA64D','glyph':'basketball','markets':{
   'single':'PRO TIP · SINGLE','points':'POINTS','rebounds':'REBOUNDS','assists':'ASSISTS','threes':'3-POINTER',
   'pra':'PTS + REB + AST','steals':'STEALS','blocks':'BLOCKS','moneyline':'MONEYLINE','spread':'SPREAD','match_total':'MATCH TOTAL'}},
}

def _sky(im,top,bot,h):
    d=ImageDraw.Draw(im)
    for y in range(h):
        t=y/h; d.line([(0,y),(W,y)],fill=tuple(int(top[i]+(bot[i]-top[i])*t) for i in range(3)))

def _lights(im,cols,y=70):
    g=Image.new('RGB',(W,H),(0,0,0)); d=ImageDraw.Draw(g)
    for cx in (110,330,540,750,970):
        d.ellipse([cx-70,y-40,cx+70,y+80],fill=cols[0]); d.polygon([(cx-40,y+60),(cx+40,y+60),(cx+330,900),(cx-330,900)],fill=cols[1])
    g=g.filter(ImageFilter.GaussianBlur(46)); return Image.blend(im,Image.composite(g,im,g.convert('L')),.85)

def make_bg(kind,path):
    im=Image.new('RGB',(W,H)); _sky(im,(3,9,22),(10,40,88),H)
    top=880
    if kind in('ice','ice_red'):
        im=_lights(im,((120,190,255),(28,64,104)))
        lay=Image.new('RGB',(W,H)); d=ImageDraw.Draw(lay)
        for y in range(top,H):
            c=int(120+90*(y-top)/(H-top)); d.line([(0,y),(W,y)],fill=(c-40,c-6,min(255,c+30)))
        red=(210,32,48) if kind=='ice' else (235,90,60)
        d.line([(0,top),(W,top)],fill=(230,245,255),width=6); d.line([(0,top+130),(W,top+130)],fill=red,width=10)
        d.line([(0,top+320),(W,top+320)],fill=(30,90,200),width=12)
        d.ellipse([W//2-230,top+160,W//2+230,top+500],outline=red,width=8)
        lay=lay.filter(ImageFilter.GaussianBlur(3))
    elif kind=='field':
        im=_lights(im,((255,240,190),(70,66,50)))
        lay=Image.new('RGB',(W,H)); d=ImageDraw.Draw(lay)
        for y in range(top-40,H):
            t=(y-top+40)/(H-top+40); d.line([(0,y),(W,y)],fill=(int(20+25*t),int(90+60*t),int(35+25*t)))
        for k in range(8):                       # mowing stripes
            d.polygon([(k*160,top-40),(k*160+80,top-40),(k*160+80-120,H),(k*160-120,H)],fill=(34,120,50))
        d.polygon([(W//2,top+10),(W//2+330,top+190),(W//2,top+420),(W//2-330,top+190)],outline=(245,245,235),width=7)
        d.ellipse([W//2-40,top+160,W//2+40,top+215],fill=(170,120,70))
        lay=lay.filter(ImageFilter.GaussianBlur(2))
    else:  # court
        im=_lights(im,((255,200,140),(80,60,48)))
        lay=Image.new('RGB',(W,H)); d=ImageDraw.Draw(lay)
        for y in range(top-30,H):
            t=(y-top+30)/(H-top+30); d.line([(0,y),(W,y)],fill=(int(150+50*t),int(88+40*t),int(40+20*t)))
        for k in range(0,W,70): d.line([(k,top-30),(k-40,H)],fill=(130,75,32),width=2)
        d.ellipse([W//2-210,top+40,W//2+210,top+330],outline=(250,240,225),width=8)
        d.line([(0,top+60),(W,top+60)],fill=(250,240,225),width=8)
        lay=lay.filter(ImageFilter.GaussianBlur(2))
    mask=Image.new('L',(W,H),0); ImageDraw.Draw(mask).rectangle([0,top-40,W,H],fill=255); mask=mask.filter(ImageFilter.GaussianBlur(10))
    im=Image.composite(Image.blend(im,lay,.9),im,mask)
    gl=Image.new('RGB',(W,H),(0,0,0)); ImageDraw.Draw(gl).ellipse([200,top+30,880,top+330],fill=(110,150,200)); gl=gl.filter(ImageFilter.GaussianBlur(70))
    im=Image.blend(im,Image.composite(gl,im,gl.convert('L')),.4)
    im.save(path,quality=90,optimize=True)

def emblem(glyph,accent):
    """Own neutral shield emblem centered in the 115x121 header box (x 38..153, y 38..159)."""
    cx,cy=96,100
    shield=f'<path d="M{cx} 48 L{cx+36} 60 V{cy+10} C{cx+36} {cy+36} {cx+16} {cy+50} {cx} {cy+58} C{cx-16} {cy+50} {cx-36} {cy+36} {cx-36} {cy+10} V60Z" fill="#06182E" stroke="{accent}" stroke-width="4"/>'
    if glyph=='puck':
        g=(f'<ellipse cx="{cx}" cy="{cy+8}" rx="21" ry="9" fill="#111"/><rect x="{cx-21}" y="{cy-4}" width="42" height="12" fill="#111"/>'
           f'<ellipse cx="{cx}" cy="{cy-4}" rx="21" ry="9" fill="#2A2F3A" stroke="{accent}" stroke-width="2"/>'
           f'<path d="M{cx-30} {cy+30} L{cx+22} {cy-26}" stroke="#F5F7FF" stroke-width="4"/><path d="M{cx+30} {cy+30} L{cx-22} {cy-26}" stroke="#F5F7FF" stroke-width="4"/>')
    elif glyph=='ball':
        g=(f'<circle cx="{cx}" cy="{cy+4}" r="23" fill="#F5F7FF" stroke="{accent}" stroke-width="2"/>'
           f'<path d="M{cx-12} {cy-16} q10 20 0 40 M{cx+12} {cy-16} q-10 20 0 40" stroke="#D8343F" stroke-width="3" fill="none"/>')
    else:
        g=(f'<circle cx="{cx}" cy="{cy+4}" r="23" fill="#F28A2E" stroke="{accent}" stroke-width="2"/>'
           f'<path d="M{cx-23} {cy+4} H{cx+23} M{cx} {cy-19} V{cy+27} M{cx-16} {cy-12} q16 16 0 32 M{cx+16} {cy-12} q-16 16 0 32" stroke="#4A230B" stroke-width="2.4" fill="none"/>')
    return f'<g id="neutral-league-emblem" data-neutral-emblem="true">{shield}{g}</g>'

LOGO_RE=re.compile(r'<image [^>]*assets/nba_logo\.png"[^>]*/>')
def adapt(svg,cfg,bg_file):
    svg=LOGO_RE.sub(emblem(cfg['glyph'],cfg['accent']),svg)
    svg=svg.replace('assets/arena.jpg',f'../assets/{bg_file}').replace('layer-01-arena-photo','layer-01-league-background')
    svg=re.sub(r'(?<![A-Z])NBA',cfg['name'],svg).replace('>ARENA<',f">{cfg['venue']}<")
    return svg

def build():
    (HERE/'assets').mkdir(exist_ok=True); manifest={'version':1,'resolution':[W,H],'production_gated':True,'leagues':{}}
    for lg,cfg in LEAGUES.items():
        out=HERE/lg; out.mkdir(exist_ok=True); bg=f'{lg}_background.jpg'; make_bg(cfg['bg'],HERE/'assets'/bg)
        nba.FAMILIES={'ladder':'NBA LADDER','builder':'NBA PROP BUILDER','same_player':'SAME PLAYER BUILDER',
                      'cross_game':'CROSS GAME BUILDER','combo':'NBA COMBO / MULTI','lottery':'NBA LOTTERY'}
        t={}
        for key,label in cfg['markets'].items():
            n=f'single_{key}'; (out/f'{n}.svg').write_text(adapt(nba.single(label),cfg,bg),encoding='utf8'); t[n]={'family':'single','legs':1,'file':f'{lg}/{n}.svg'}
        for fam in nba.FAMILIES:
            for n in range(2,7):
                k=f'{fam}_{n}'; (out/f'{k}.svg').write_text(adapt(nba.multi(fam,n),cfg,bg),encoding='utf8'); t[k]={'family':fam,'legs':n,'file':f'{lg}/{k}.svg'}
        manifest['leagues'][lg]={'name':cfg['name'],'template_count':len(t),'templates':t}
    (HERE/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return manifest

def render(lg,key):
    m=json.loads((HERE/'manifest.json').read_text()); f=HERE/m['leagues'][lg]['templates'][key]['file']
    bg=f"{lg}_background.jpg"; svg=f.read_text().replace(f'../assets/{bg}','data:image/jpeg;base64,'+base64.b64encode((HERE/'assets'/bg).read_bytes()).decode())
    return cairosvg.svg2png(bytestring=svg.encode(),output_width=W)

def previews():
    out=HERE/'previews'; out.mkdir(exist_ok=True)
    for lg in LEAGUES:
        for k in ('single_single','ladder_4','builder_4','lottery_6'):
            (out/f'{lg}_{k}.png').write_bytes(render(lg,k))
    return len(list(out.glob('*.png')))

if __name__=='__main__':
    m=build(); print({k:v['template_count'] for k,v in m['leagues'].items()}); print('previews',previews())
