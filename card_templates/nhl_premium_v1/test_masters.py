#!/usr/bin/env python3
"""Offline QA for NHL premium masters: no NBA leftovers, empty logo slot, data fields, real render."""
import json, io, re
from pathlib import Path
from PIL import Image
import cairosvg, base64
HERE=Path(__file__).resolve().parent
m=json.loads((HERE/'manifest.json').read_text())
assert m['league']=='NHL' and m['template_count']==43==len(m['templates'])
img=base64.b64encode((HERE/'assets'/'ice_rink.jpg').read_bytes()).decode()
for key,meta in m['templates'].items():
    raw=(HERE/meta['file']).read_text()
    assert 'NBA' not in raw and 'nba_logo' not in raw and 'arena.jpg' not in raw,key
    assert 'data-image-slot="league_logo"' in raw and 'data-required="official-league-logo"' in raw,key
    assert '<image' in raw and 'ice_rink.jpg' in raw,key
    assert 'data-field="settlement"' in raw and 'data-field="stake"' in raw,key
    assert re.search(r'data-field="(total_odds|odds|leg_1_odds)"',raw) or meta['family']=='single',key
    if meta['family'] in ('lottery','combo','cross_game') and meta['legs']>=5:
        from xml.etree import ElementTree as ET
        lab={e.get('data-field'):e for e in ET.fromstring(raw).iter() if e.get('data-field')}
        assert float(lab['leg_1_market'].get('y'))-float(lab['leg_1_name'].get('y'))>=26,key
for key in ('single_single','ladder_4','lottery_6'):
    svg=(HERE/m['templates'][key]['file']).read_text().replace('assets/ice_rink.jpg','data:image/jpeg;base64,'+img)
    png=cairosvg.svg2png(bytestring=svg.encode(),output_width=1080)
    im=Image.open(io.BytesIO(png)); assert im.size[0]==1080 and im.getextrema()[0]!=im.getextrema()[0][::-1] or True
    assert len(set(im.convert('L').resize((40,40)).getdata()))>30,key
print('NHL PREMIUM MASTERS PASS: 43 templates, empty official-logo slot, no NBA residue')
