#!/usr/bin/env python3
"""Offline QA for NHL multi-player masters: 20 templates, slots + fields per leg, logo, no baked data."""
import json, re
from pathlib import Path
HERE=Path(__file__).resolve().parent
m=json.loads((HERE/'nhl_multi'/'manifest.json').read_text())['templates']
assert len(m)==20
for k,t in m.items():
    raw=(HERE/t['file']).read_text(); n=t['legs']
    assert 'data-official-league-logo="owner-supplied"' in raw and 'nba_logo' not in raw and 'arena.jpg' not in raw,k
    for f in ('settlement','stake'): assert f'data-field="{f}"' in raw,(k,f)
    for i in range(1,n+1):
        assert f'data-field="leg_{i}_odds"' in raw,(k,i)
        if t['family']=='ladder': assert f'data-field="leg_{i}_line"' in raw,(k,i)
        else: assert f'data-image-slot="leg_{i}_photo"' in raw and f'data-field="leg_{i}_name"' in raw,(k,i)
    assert f'data-field="leg_{n+1}_odds"' not in raw,k
    if t['family']=='ladder': assert 'data-image-slot="player_photo"' in raw,k
    else: assert 'data-field="total_odds"' in raw,k
    assert not re.search(r'data-field="[a-z_0-9]+"[^>]*>[^<]+<',raw),k      # nothing baked into a field
print('NHL MULTI MASTERS PASS: 20 templates, slots/fields per leg, owner logo, no baked data')
