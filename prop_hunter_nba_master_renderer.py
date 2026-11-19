#!/usr/bin/env python3
"""Safe dynamic filler for clean NBA SVG masters; not wired to live Telegram.

All player photos, logos, names, prices and stats are independent editable
elements. No screenshot samples are painted over or hidden with rectangles.
"""
from __future__ import annotations
import base64,io,json
from pathlib import Path
from xml.etree import ElementTree as ET
from PIL import Image

ROOT=Path(__file__).resolve().parent/'card_templates'/'nba_masters'
SVG='http://www.w3.org/2000/svg'
XLINK='http://www.w3.org/1999/xlink'
ET.register_namespace('',SVG)
ET.register_namespace('xlink',XLINK)

def render_svg(template_key: str, values: dict, images: dict[str,bytes]|None=None,
               *, require_verified_odds:bool=True)->str:
    """Fill a master using only caller-supplied data; never infer a combo price.

    images: local PNG bytes for player_photo, home_logo, away_logo, leg_N_photo.
    Player portraits must be transparent cutouts (not opaque photo rectangles).
    """
    manifest=json.loads((ROOT/'manifest.json').read_text(encoding='utf8'))
    key=str(template_key or '').strip()
    item=manifest['templates'].get(key)
    if not item:raise ValueError('Unknown NBA master: '+key)
    if not isinstance(values,dict):raise TypeError('values must be a dictionary')
    images=images or {}
    if not isinstance(images,dict):raise TypeError('images must be a dictionary')
    tree=ET.fromstring((ROOT/item['file']).read_text(encoding='utf8'))
    fields={e.get('data-field') for e in tree.iter() if e.get('data-field')}
    if require_verified_odds:
        quote='total_odds' if 'total_odds' in fields else 'odds'
        if not values.get('odds_verified') or not str(values.get(quote) or '').strip():
            raise ValueError('Only verified bookmaker odds; never estimate or multiply combo prices')
    for e in tree.iter():
        field=e.get('data-field')
        if not field:continue
        raw=values.get(field)
        e.text=str(raw).strip() if raw is not None else ('OFFEN' if field=='settlement' else '')
        if not e.text:continue
        size=float(e.get('font-size') or 28)
        if field in {'player_name','market','game'} and len(e.text)>18:
            e.set('font-size',str(max(24,round(size*18/len(e.text)))))
        elif field.endswith(('_name','_market')) and len(e.text)>24:
            e.set('font-size',str(max(16,round(size*24/len(e.text)))))
    for g in tree.iter():
        slot=g.get('data-image-slot')
        if not slot or slot not in images or images[slot] is None:continue
        raw=images[slot]
        if not isinstance(raw,bytes):raise TypeError(slot+': image must be local PNG bytes')
        try:
            im=Image.open(io.BytesIO(raw));im.load()
        except Exception as ex:raise ValueError(slot+': corrupt PNG') from ex
        if im.format!='PNG':raise ValueError(slot+': PNG required')
        player=slot=='player_photo' or slot.endswith('_photo')
        if player and im.convert('RGBA').getchannel('A').getextrema()[0]==255:
            raise ValueError(slot+': transparent player cutout required; no framed photo')
        for child in list(g):
            if child.get('data-placeholder')=='true':g.remove(child)
        pic=ET.Element(f'{{{SVG}}}image',{
            'x':g.get('data-x'),'y':g.get('data-y'),
            'width':g.get('data-width'),'height':g.get('data-height'),
            'preserveAspectRatio':'xMidYMax meet' if player else 'xMidYMid meet',
            'data-filled-image-slot':slot})
        pic.set(f'{{{XLINK}}}href','data:image/png;base64,'+base64.b64encode(raw).decode('ascii'))
        g.insert(0 if player else 1,pic)
    return ET.tostring(tree,encoding='unicode')

def render_png(template_key:str, values:dict, images:dict[str,bytes]|None=None,
               *,require_verified_odds:bool=True)->bytes:
    """Rasterize the master, without publishing to Telegram."""
    import cairosvg
    svg=render_svg(template_key,values,images,require_verified_odds=require_verified_odds)
    return cairosvg.svg2png(bytestring=svg.encode('utf8'),output_width=1080,output_height=1440)
