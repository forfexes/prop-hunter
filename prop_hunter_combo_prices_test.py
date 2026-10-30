from copy import deepcopy
from types import SimpleNamespace
from prop_hunter_combo_prices import publishable_extra,unpriced_sgp,invalidate_unpriced_combo
from prophunter_results import _performance_rows,_decorate_card

legs=[dict(player='Zach Edey',market='Rebounds Over 13.5',odds=12,game='Memphis @ Portland'),
      dict(player='Ja Morant',market='Assists Over 9.5',odds=7,game='Memphis @ Portland'),
      dict(player='Jrue Holiday',market='Points Over 19.5',odds=6.4,game='Memphis @ Portland')]
p=dict(type='big',odds=537.6,leg_details=legs,features={'odds_observed':True,'price_type':'bookmaker'},result='win',profit=26.83,combo_id='lottery')
assert unpriced_sgp(p) and not publishable_extra(p)
assert not publishable_extra(SimpleNamespace(**p))
assert not _performance_rows([{'kombis':[p]}])
assert invalidate_unpriced_combo(p) and p['result']=='withdrawn'
assert p['quote_original_profit']==26.83
assert not invalidate_unpriced_combo(p)
card=dict(text='LOTTERY @537.60\n📈 Prob 1.0% · EV +461.4%\n🏁 Auswertung: offen',combo_ids=['lottery'])
text=_decorate_card(card,[],[p])
assert 'keine bestätigte Buchmacherquote' in text and '461.4%' not in text and 'Drittelquote' not in text
observed=deepcopy(p);observed['features']=dict(combined_odds_observed=True,combined_quote_id='book-ticket-123')
assert publishable_extra(observed) and not unpriced_sgp(observed)
cross=deepcopy(p)
for i,leg in enumerate(cross['leg_details']):leg['game']=f'A{i} @ B{i}'
assert publishable_extra(cross) and not unpriced_sgp(cross)
# Two same-game legs plus another game still contain an unpriced SGP component.
cross['leg_details'][1]['game']=cross['leg_details'][0]['game']
assert not publishable_extra(cross)
assert publishable_extra(dict(type='ladder',odds=12))
assert publishable_extra(dict(type='single',odds=12))
assert not publishable_extra(dict(type='big',odds=12))
import json
history=json.load(open('picks_history.json'))
affected=[p for e in history for p in e.get('kombis',[]) if not p.get('quote_invalidated') and unpriced_sgp(p)]
print(f'COMBO PRICE REGRESSIONS PASSED; retained unpriced SGPs={len(affected)}')
# Execute the actual production extras assembly block with a synthetic builder
# result: rejection must happen before the main function formats/persists picks.
import ast,sys
from pathlib import Path
from types import ModuleType
from unittest.mock import patch
module=ast.parse(Path('prophunter_core_1391.py').read_text())
main=next(n for n in module.body if isinstance(n,ast.FunctionDef) and n.name=='run')
block=next(n for n in ast.walk(main) if isinstance(n,ast.Try) and any(isinstance(x,ast.ImportFrom) and x.module=='prop_hunter_builder_engine' for x in n.body))
code=compile(ast.fix_missing_locations(ast.Module(body=[block],type_ignores=[])),'production-extras','exec')
fake=ModuleType('prop_hunter_builder_engine')
invalid=SimpleNamespace(**dict(p,quote_invalidated=False))
single=SimpleNamespace(type='single')
fake.build_autonomous_extras=lambda *args:[invalid,single]
ns=dict(picks=[],props=[],Pick=object,LadderLeg=object,log=SimpleNamespace(info=lambda *a:None,warning=lambda *a:None))
with patch.dict(sys.modules,{'prop_hunter_builder_engine':fake}):exec(code,ns)
assert ns['picks']==[single], 'unpriced SGP reached production delivery'
print('PRODUCTION DELIVERY PRICE GATE PASSED')
