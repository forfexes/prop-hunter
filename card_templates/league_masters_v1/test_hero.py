#!/usr/bin/env python3
"""Offline QA for hero singles: slots/fields present, no baked data, renders to 1080x1440."""
import io, re
from pathlib import Path
from PIL import Image
import hero_single as h
for lg in ('nhl','ahl'):
    raw=(h.HERE/'hero'/f'{lg}_single_hero.svg').read_text()
    for slot in ('player_photo','home_logo','away_logo'): assert f'data-image-slot="{slot}"' in raw,(lg,slot)
    for f in ('player_name','matchup','market','odds','l5','l10','l15','settlement','stake'): assert f'data-field="{f}"' in raw,(lg,f)
    assert 'data-neutral-emblem="true"' in raw and 'nba_logo' not in raw and 'arena.jpg' not in raw,lg
    assert not re.search(r'data-field="odds"[^>]*>[^<]+<',raw),lg      # no baked price
    im=Image.open(io.BytesIO(h.render(lg))); assert im.size==(1080,1440)
    assert len(set(im.convert('L').resize((40,40)).getdata()))>40,lg
print('HERO SINGLE MASTERS PASS: 2 leagues, slots + fields, no baked data')
