#!/usr/bin/env python3
"""Offline QA: league masters carry no NBA residue, have the neutral emblem, background file, data fields."""
import json, re
from pathlib import Path
HERE=Path(__file__).resolve().parent
m=json.loads((HERE/'manifest.json').read_text())
assert {k:v['template_count'] for k,v in m['leagues'].items()}=={'nhl':43,'ahl':38,'mlb':40,'wnba':41}
for lg,L in m['leagues'].items():
    assert (HERE/'assets'/f'{lg}_background.jpg').is_file(),lg
    for key,t in L['templates'].items():
        raw=(HERE/t['file']).read_text()
        assert 'nba_logo' not in raw and 'arena.jpg' not in raw and 'WWNBA' not in raw,(lg,key)
        if lg!='wnba': assert not re.search(r'(?<![A-Z])NBA',raw),(lg,key)
        assert 'data-neutral-emblem="true"' in raw and f'../assets/{lg}_background.jpg' in raw,(lg,key)
        assert 'data-field="settlement"' in raw and 'data-field="stake"' in raw,(lg,key)
print('LEAGUE MASTERS PASS: NHL 43, AHL 38, MLB 40, WNBA 41; neutral emblems, no NBA residue')
