#!/usr/bin/env python3
"""NHL hero single using the OWNER-SUPPLIED hall photo and OWNER-SUPPLIED NHL logo.

Two background variants:
  blur   - photo cropped to the empty right side, blurred, darkened: neutral arena behind a runtime player cut-out
  player - un-blurred crop that keeps the supplied skater (look reference; no cut-out needed)
Both keep all data in named fields/slots; the logo sits in the header, never redrawn.
"""
import base64, re, sys
from pathlib import Path
import cairosvg
import hero_single as hs
HERE=hs.HERE; nba=hs.nba

def build_svg(bg):
    svg=hs.hero('nhl',hs.league.LEAGUES['nhl'])
    svg=svg.replace('../assets/nhl_hero_bg.jpg',f'../assets/{bg}')
    a=svg.index('<g id="layer-03-emblem"'); b=svg.index('<g id="layer-04-frameless-athlete">')
    logo='<g id="layer-03-league-logo"><image x="26" y="18" width="124" height="124" preserveAspectRatio="xMidYMid meet" xlink:href="../assets/nhl_logo_owner_supplied.png" data-official-league-logo="owner-supplied"/></g>'
    return svg[:a]+logo+svg[b:]

def render(svg,values=None):
    for m in set(re.findall(r'xlink:href="\.\./assets/([^"]+)"',svg)):
        mime='image/png' if m.endswith('.png') else 'image/jpeg'
        svg=svg.replace(f'../assets/{m}',f'data:{mime};base64,'+base64.b64encode((HERE/'assets'/m).read_bytes()).decode())
    if values:
        for k,v in values.items():
            svg=re.sub(r'(data-field="%s"[^>]*>)(</text>)'%k,lambda m:m.group(1)+str(v).replace('&','&amp;')+m.group(2),svg)
    return cairosvg.svg2png(bytestring=svg.encode(),output_width=1080)

SAMPLE={'player_name':'SPIELERNAME','matchup':'HEIM @ AUSWÄRTS','market':'ÜBER 2,5 SCHÜSSE','odds':'1,85','l5':'4/5','l10':'7/10','l15':'10/15','settlement':'OFFEN','stake':'1U'}
if __name__=='__main__':
    out=HERE/'hero'; pv=HERE/'previews'
    for name,bg in (('blur','nhl_hero_bg_photo_blur.jpg'),('player','nhl_hero_bg_photo_player.jpg')):
        svg=build_svg(bg); (out/f'nhl_single_hero_official_{name}.svg').write_text(svg,encoding='utf8')
        (pv/f'hero_nhl_official_{name}_leer.png').write_bytes(render(svg)); (pv/f'hero_nhl_official_{name}_beispiel.png').write_bytes(render(svg,SAMPLE))
    print('ok')
