import io,json,sys
from pathlib import Path
from PIL import Image,ImageDraw
from render_cards import ROOT,render_svg,render_png
m=json.loads((ROOT/'manifest.json').read_text())
assert m['template_count']==52
assert len(list(ROOT.glob('*.svg')))==52
for key,meta in m['templates'].items():
    raw=(ROOT/meta['file']).read_text()
    assert 'assets/arena.jpg' in raw,key
    assert 'data-field="settlement"' in raw,key
    if meta['family'] not in ('lottery','combo','cross_game'):
        assert 'data-image-slot="home_logo"' in raw,key
        assert 'data-image-slot="away_logo"' in raw,key
    else:
        assert 'data-image-slot="home_logo"' not in raw,key
        assert f'data-field="leg_{meta["legs"]}_game"' in raw,key
    assert 'SPIELERNAME' not in raw,key
    assert '@1.72' not in raw,key
    assert 'Jokic' not in raw,key
    assert '1 offen' not in raw,key
    assert 'PRO TIP</text>' not in raw,key
    assert 'layer-01-arena-photo' in raw,key
    assert 'data-static-nba-logo="true"' in raw,key
    assert 'assets/nba_logo.png' in raw,key
    assert '>PROPS</text>' not in raw,key
    assert 'data-field="True"' not in raw,key
    if meta['family'] in ('lottery','combo','cross_game') and meta['legs']>=5:
        # Realistic 6-leg text must never overlap its neighboring row labels.
        from xml.etree import ElementTree as ET
        root=ET.fromstring(raw)
        labels={e.get('data-field'):e for e in root.iter() if e.get('data-field')}
        name=labels['leg_1_name'];market=labels['leg_1_market'];game=labels['leg_1_game']
        assert float(market.get('y'))-float(name.get('y'))>=26,key
        assert float(game.get('y'))-float(market.get('y'))>=20,key
    if meta['family'] in ('ladder','same_player'):
        assert raw.count('data-image-slot="player_photo"')==1,key
    if meta['family'] in ('builder','lottery','cross_game'):
        assert sum(raw.count(f'data-image-slot="leg_{i}_photo"') for i in range(1,7))==meta['legs'],key
for key in ('single_single','ladder_4','builder_6','combo_5','lottery_6'):
    try:render_svg(key,{},{});
    except ValueError as exc:assert 'odds' in str(exc)
    else:raise AssertionError('Unverified odds passed '+key)
portrait=Image.new('RGBA',(80,140),(0,0,0,0));ImageDraw.Draw(portrait).ellipse((20,10,65,80),fill=(70,130,190,255))
b=io.BytesIO();portrait.save(b,'PNG')
logo=Image.new('RGBA',(80,80),(0,0,0,0));ImageDraw.Draw(logo).ellipse((5,5,75,75),fill=(220,120,20,255))
c=io.BytesIO();logo.save(c,'PNG')
values={'odds_verified':True,'odds':'2.05','date':'20.11.2026','time':'20:00','home_name':'HEIM',
        'away_name':'GAST','market':'TEST ONLY','player_name':'TEST ATHLETE','settlement':'OFFEN'}
imgs={'player_photo':b.getvalue(),'home_logo':c.getvalue(),'away_logo':c.getvalue()}
raw=render_png('single_single',values,imgs)
assert Image.open(io.BytesIO(raw)).size==(1080,1440)
try:render_svg('single_single',{**values,'odds_verified':False},imgs)
except ValueError as e:assert 'verified' in str(e)
else:raise AssertionError('Odds verification guard failed')
opaque=Image.new('RGB',(100,100),'red');d=io.BytesIO();opaque.save(d,'PNG')
try:render_svg('single_single',values,{**imgs,'player_photo':d.getvalue()})
except ValueError as e:assert 'transparent' in str(e)
else:raise AssertionError('Opaque portrait accepted')
print('52/52 PREMIUM MASTERS PASS; live odds gate; alpha portrait; real PNG; no baked player/logo/quote')
