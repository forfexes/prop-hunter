#!/usr/bin/env python3
"""NHL multi-player masters (Ladder, Builder, Kombi, Lottery; 2-6 legs) in the hero style (variant B).

Owner-supplied hall photo (blurred) + owner-supplied NHL logo. Every changing value is a named
data-field / data-image-slot; nothing is baked. Not production-wired (design proposal).
"""
import json, re
from pathlib import Path
import hero_nhl_official as ho
hs=ho.hs; nba=hs.nba
HERE=ho.HERE; W,H=1080,1440
ACC={'ladder':'#35C9FF','builder':'#35C9FF','combo':'#35C9FF','lottery':'#D83AFF'}
LABEL={'ladder':'NHL LADDER','builder':'NHL PROP BUILDER','combo':'NHL KOMBI / MULTI','lottery':'NHL LOTTERY'}
WHITE='#F5F9FF'; MUTED='#A9C9DE'; GOLD='#FFD66B'

def header(label,acc):
    svg=ho.build_svg('nhl_multi_bg.jpg')
    head=svg[:svg.index('<g id="layer-04-frameless-athlete">')]
    head=head.replace('NHL SINGLE',label).replace('#35C9FF',acc).replace('M150 170 H345','M50 170 H190').replace('M735 170 H930','M890 170 H1030')
    return head

def glass(x,y,w,h,acc):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="16" fill="#04101F" fill-opacity=".66" stroke="{acc}" stroke-opacity=".75" stroke-width="2.2"/>')

def footer(acc,total):
    s='<g id="layer-12-footer">'
    if total:
        s+=nba.txt(540,1290,'GESAMTQUOTE',28,MUTED,'middle',italic=True)+nba.dynamic(540,1380,'total_odds',88,'#FFFFFF','middle',True,max_width=640)
    s+=nba.txt(60,1428,'AUSWERTUNG:',22,MUTED,italic=True)+nba.dynamic(262,1428,'settlement',24,GOLD,'start',True,max_width=340)
    s+=nba.txt(640,1428,'EINSATZ',22,MUTED,italic=True)+nba.dynamic(770,1428,'stake',24,GOLD,'start',True,max_width=120)
    s+=nba.txt(1030,1428,'@prophunter',24,WHITE,'end',italic=True)+'</g>'
    return s

def ladder(n):
    acc=ACC['ladder']; s=header(f'{LABEL["ladder"]} · {n} LEGS',acc)
    s+=f'<g id="layer-04-frameless-athlete">{nba.asset_slot("player_photo",270,196,540,430)}</g>'
    s+=f'<g id="layer-05-matchup">{nba.asset_slot("home_logo",120,664,76,76)}{nba.asset_slot("away_logo",884,664,76,76)}'
    s+=nba.dynamic(540,716,'player_name',66,WHITE,'middle',True,max_width=640)+nba.dynamic(540,758,'matchup',30,MUTED,'middle',True,max_width=640)+'</g>'
    top,bot,gap=786,1262,8; rh=min(92,(bot-top-gap*(n-1))/n)
    s+='<g id="layer-08-legs">'
    for i in range(1,n+1):
        y=round(top+(i-1)*(rh+gap)); s+=f'<g id="layer-leg-{i}">'+glass(60,y,960,round(rh),acc)
        s+=nba.txt(96,y+rh*.62,f'{i}.',34,acc,'middle',italic=True)
        s+=nba.dynamic(140,y+rh*.46,f'leg_{i}_line',min(38,int(rh*.42)),WHITE,'start',True,max_width=560)
        s+=nba.dynamic(140,y+rh*.84,f'leg_{i}_form',min(22,int(rh*.24)),MUTED,'start',False,max_width=560)
        s+=nba.dynamic(990,y+rh*.64,f'leg_{i}_odds',min(52,int(rh*.52)),'#FFFFFF','end',True,max_width=240)+'</g>'
    return s+'</g>'+footer(acc,False)+'</svg>'

def multi(family,n):
    acc=ACC[family]; s=header(f'{LABEL[family]} · {n} LEGS',acc)
    if family=='builder':
        s+=f'<g id="layer-05-matchup">{nba.asset_slot("home_logo",160,196,96,96)}{nba.asset_slot("away_logo",824,196,96,96)}'
        s+=nba.dynamic(540,258,'matchup',44,WHITE,'middle',True,max_width=520)+'</g>'; top=318
    else:
        s+=nba.txt(540,232,'INDIVIDUELLE SPIELERPROPS',26,MUTED,'middle',italic=True); top=262
    bot,gap=1262-120,10; rh=min(150,(bot-top-gap*(n-1))/n)
    s+='<g id="layer-08-legs">'
    for i in range(1,n+1):
        y=round(top+(i-1)*(rh+gap)); ph=round(min(rh-8,118)); s+=f'<g id="layer-leg-{i}">'+glass(40,y,1000,round(rh),acc)
        s+=nba.txt(78,y+rh*.58,f'{i}.',32,acc,'middle',italic=True)
        s+=nba.asset_slot(f'leg_{i}_photo',112,y+4,ph,round(rh-8))
        tx=112+ph+18; tw=1000-(tx-40)-230
        s+=nba.dynamic(tx,y+rh*.34,f'leg_{i}_name',min(34,int(rh*.27)),WHITE,'start',True,max_width=tw)
        s+=nba.dynamic(tx,y+rh*.60,f'leg_{i}_market',min(28,int(rh*.22)),acc if family!='lottery' else '#E9A6FF','start',True,max_width=tw)
        s+=nba.dynamic(tx,y+rh*.84,f'leg_{i}_form',min(21,int(rh*.17)),MUTED,'start',False,max_width=tw)
        s+=nba.dynamic(1015,y+rh*.62,f'leg_{i}_odds',min(52,int(rh*.4)),'#FFFFFF','end',True,max_width=210)+'</g>'
    return s+'</g>'+footer(acc,True)+'</svg>'

def build():
    out=HERE/'nhl_multi'; out.mkdir(exist_ok=True); t={}
    for fam in ('ladder','builder','combo','lottery'):
        for n in range(2,7):
            k=f'{fam}_{n}'; (out/f'{k}.svg').write_text(ladder(n) if fam=='ladder' else multi(fam,n),encoding='utf8'); t[k]={'family':fam,'legs':n,'file':f'nhl_multi/{k}.svg'}
    (out/'manifest.json').write_text(json.dumps({'league':'NHL','style':'B-blur-hall','templates':t},indent=2)+'\n'); return t

SAMPLE_LEG=lambda i:{f'leg_{i}_name':f'SPIELER {i}',f'leg_{i}_market':'ÜBER 2,5 SCHÜSSE',f'leg_{i}_form':'L5 4/5 · L10 7/10 · L15 10/15',f'leg_{i}_odds':'1,85',f'leg_{i}_line':f'{i+1}+ SCHÜSSE'}
def sample(n):
    v={'player_name':'SPIELERNAME','matchup':'HEIM @ AUSWÄRTS','total_odds':'12,40','settlement':'OFFEN','stake':'1U'}
    for i in range(1,n+1): v.update(SAMPLE_LEG(i))
    return v
if __name__=='__main__':
    t=build(); pv=HERE/'previews'
    for k,m in t.items():
        svg=(HERE/m['file']).read_text()
        if k in('ladder_4','builder_4','combo_5','lottery_6','builder_2','ladder_2','combo_6'):
            (pv/f'nhl_multi_{k}.png').write_bytes(ho.render(svg,sample(m['legs'])))
    print(len(t))
