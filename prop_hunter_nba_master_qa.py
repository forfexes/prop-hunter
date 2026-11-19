#!/usr/bin/env python3
"""52-layer NBA master QA. Test-only synthetic inputs are NEVER sent to Telegram."""
import io,json,math
from pathlib import Path
from xml.etree import ElementTree as ET
from PIL import Image,ImageDraw,ImageFont
import cairosvg
from prop_hunter_nba_master_renderer import ROOT,render_svg,render_png

manifest=json.loads((ROOT/'manifest.json').read_text(encoding='utf8'))
templates=manifest['templates']
assert len(templates)==52
assert len(list(ROOT.glob('*.svg')))==52
for key,item in templates.items():
    raw=(ROOT/item['file']).read_text(encoding='utf8')
    tree=ET.fromstring(raw)
    slots=[e.get('data-image-slot') for e in tree.iter() if e.get('data-image-slot')]
    fields={e.get('data-field') for e in tree.iter() if e.get('data-field')}
    assert len(slots)==len(set(slots)),key
    assert 'settlement' in fields,key
    assert 'data:image/' not in raw,key
    for sample in ('Stephen Curry','Nikola Jokic','Golden State Warriors','1.90','1 offen · +0.00u'):
        assert sample not in raw,(key,sample)
    if item['family'] in ('ladder','same_player'):
        assert slots.count('player_photo')==1
        assert not any(s.endswith('_photo') and s!='player_photo' for s in slots)
    if item['family'] in ('builder','cross_game'):
        assert sum(s.endswith('_photo') for s in slots)==item['legs'],key
    if item['family'] in ('single','longshot'):
        assert {'player_photo','home_logo','away_logo'}.issubset(slots),key
    if item['legs']>1:
        assert f'leg_{item["legs"]}_market' in fields,key
        assert 'total_odds' in fields,key

for k in ('single_single','builder_6','ladder_3','lottery_5'):
    try:render_svg(k,{})
    except ValueError as e:assert 'verified bookmaker odds' in str(e)
    else:raise AssertionError('Unverified quote accepted: '+k)

photo=Image.new('RGBA',(150,220),(0,0,0,0))
d=ImageDraw.Draw(photo)
d.ellipse((30,8,128,112),fill=(150,165,180,255))
d.rounded_rectangle((5,108,147,219),20,fill=(25,90,150,255))
buf=io.BytesIO();photo.save(buf,format='PNG')
fake={'odds_verified':True,'odds':'2.00','player_name':'TEST ONLY','market':'NO REAL PICK',
      'settlement':'OFFEN','tipoff':'TEST ONLY'}
svg=render_svg('single_single',fake,{'player_photo':buf.getvalue()})
assert 'data-filled-image-slot="player_photo"' in svg
assert 'TEST ONLY' in svg and 'SPIELERNAME' not in svg
img=Image.open(io.BytesIO(render_png('single_single',fake,{'player_photo':buf.getvalue()})))
assert img.size==(1080,1440)
bad=Image.new('RGB',(150,220),'red');b=io.BytesIO();bad.save(b,format='PNG')
try:render_svg('single_single',fake,{'player_photo':b.getvalue()})
except ValueError as e:assert 'transparent player cutout' in str(e)
else:raise AssertionError('Opaque portrait was accepted')

keys=['single_single','single_points','single_rebounds','single_assists','ladder_2',
      'ladder_4','ladder_6','builder_2','builder_4','builder_6','same_player_3',
      'cross_game_4','combo_3','lottery_5','longshot']
cols=5;w=340;h=453;pad=22;caption=50
overview=Image.new('RGB',(pad+cols*(w+pad),pad+3*(h+caption+pad)),(3,9,23))
draw=ImageDraw.Draw(overview)
try:font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',19)
except OSError:font=ImageFont.load_default()
for i,key in enumerate(keys):
    x=pad+(i%cols)*(w+pad);y=pad+(i//cols)*(h+caption+pad)
    svg=(ROOT/templates[key]['file']).read_bytes()
    rendered=cairosvg.svg2png(bytestring=svg,output_width=w,output_height=h)
    im=Image.open(io.BytesIO(rendered)).convert('RGB')
    overview.paste(im,(x,y))
    draw.text((x+5,y+h+8),key.replace('_',' ').upper(),font=font,fill=(255,211,107))
out=Path('diagnostics/nba_master_visual_qa.png')
out.parent.mkdir(parents=True,exist_ok=True)
overview.save(out,optimize=True)
print('NBA_MASTER_QA: 52/52 layered masters passed; single/ladders/builders/lottery; 2-6 legs; transparent photos; verified odds; rendered contact sheet:',out,flush=True)
