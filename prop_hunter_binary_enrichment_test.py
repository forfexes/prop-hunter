#!/usr/bin/env python3
"""Run the production enrichment function with observed L15 fixtures, without I/O."""
import ast
import logging
import os
import re
from datetime import date, timedelta, datetime, timezone
from pathlib import Path
from types import SimpleNamespace


def main():
    tree = ast.parse(Path('prophunter_core_1391.py').read_text())
    fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'enrich_gamelogs_fairprob')
    rows = []
    for i in range(15):
        rows.append({'normalized_name': 'fixture player', 'game_date': (date(2026,10,27)-timedelta(days=i)).isoformat(),
                     'league':'NBA','steals':0,'blocks':0,'points': 20 if i < 9 else 5, 'rebounds': 12 if i < 9 else 2, 'assists': 11 if i < 4 else 3})
    rows.append({'normalized_name': 'fixture player', 'game_date': '2026-01-01', 'points': 99, 'rebounds': 99, 'assists': 99})
    class Query:
        @property
        def not_(self): return self
        def table(self,*a,**k): return self
        def select(self,*a,**k): return self
        def in_(self,*a,**k): return self
        def is_(self,*a,**k): return self
        def order(self,*a,**k): return self
        def limit(self,*a,**k): return self
        def eq(self,*a,**k): return self
        def execute(self): return SimpleNamespace(data=rows)
    scope = {'_sb_read': lambda: Query(), '_GAMELOG_CACHE': {},
             'norm_name': lambda value: ' '.join(str(value).lower().split()),
             'log': logging.getLogger('fixture'), 'os': os, 're': re, 'datetime':datetime, 'timezone':timezone}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), '<production enrichment>', 'exec'), scope)
    def prop(market):
        return SimpleNamespace(player='Fixture Player', market=market, sport='NBA', point=None,
                               odds=3, commence_time='2026-10-30T02:00Z', features={}, enrichment='', direction='over')
    dd, td, numeric = prop('Double Double'), prop('Triple Double'), prop('Points')
    scope['enrich_gamelogs_fairprob']([dd, td, numeric])
    assert dd.features['gamelog_n'] == td.features['gamelog_n'] == 15
    assert dd.features['gamelog_dd_rate'] == .6, dd.features
    assert td.features['gamelog_dd_rate'] == .267, td.features
    assert abs(dd.features['fair_prob'] - .6) < 1e-9
    assert numeric.features == {}, 'numeric props without an observed line must remain unenriched'
    print('BINARY DD/TD REAL L15 ENRICHMENT TEST PASSED')


if __name__ == '__main__':
    main()
