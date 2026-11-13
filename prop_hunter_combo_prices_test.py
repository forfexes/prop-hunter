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

# The final fence also covers combos returned by analysis/rescue, not only extras.
main=next(n for n in ast.parse(Path('prophunter_core_1391.py').read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='run')
fence=next(n for n in main.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='picks' for t in n.targets) and isinstance(n.value,ast.ListComp) and 'publishable_extra' in ast.unparse(n))
ns=dict(picks=[invalid,single],publishable_extra=publishable_extra)
exec(compile(ast.fix_missing_locations(ast.Module(body=[fence],type_ignores=[])),'production-final-fence','exec'),ns)
assert ns['picks']==[single]
print('PRODUCTION FINAL PRICE FENCE PASSED')

# Cross-Game-Builder (verschiedene, unabhaengige Spiele): das Quoten-PRODUKT
# ist mathematisch korrekt, also KEIN unpriced SGP — darf weder neu
# invalidiert noch zurueckgehalten werden, auch wenn aus Einzelquoten abgeleitet.
wrong=dict(type='betbuilder',odds=3.94,result='withdrawn',status='withdrawn',profit=None,
    quote_invalidated=True,quote_original_result='loss',quote_original_profit=-.1,
    quote_invalidation_reason='Same-Game-Gesamtquote nur aus Einzelquoten berechnet; keine bestätigte Buchmacherquote',
    features=dict(combo_scope='cross_game',price_type='derived_acca',builder_odds_estimated_from_legs=True),
    leg_details=[dict(player='Both Teams Total',odds=1.95,game='MEM Grizzlies @ POR Trail Blazers'),
                 dict(player='CJ McCollum',odds=2.02,game='CLE Cavaliers @ ATL Hawks')])
# Cross-Game ist kein unpriced SGP (mehr):
assert not unpriced_sgp(wrong)
# Ein frischer (noch nicht invalidierter) Cross-Game-Builder wird NICHT invalidiert:
fresh_cross=deepcopy(wrong); fresh_cross.pop('quote_invalidated'); fresh_cross.pop('quote_original_result'); fresh_cross.pop('quote_original_profit')
fresh_cross.update(result='win',profit=0.33)
assert not invalidate_unpriced_combo(fresh_cross)
assert fresh_cross['result']=='win' and fresh_cross['profit']==0.33, 'cross-game darf nicht zurueckgehalten werden'
# Ein bereits invalidierter Alt-Ticket bleibt withdrawn (keine Reaktivierung):
assert not invalidate_unpriced_combo(wrong)
assert wrong['result']=='withdrawn'
# Echter unpriced Fall: fehlendes Spiel-Label -> Kombi-Grund, wird invalidiert.
unknown=deepcopy(wrong);unknown.pop('quote_invalidated');unknown.pop('quote_original_result');unknown.pop('quote_original_profit')
unknown['features']=dict(price_type='derived_builder')  # kein cross_game-scope
unknown['leg_details'][0]['game']='';unknown['leg_details'][1]['game']=''
assert invalidate_unpriced_combo(unknown) and unknown['quote_invalidation_reason'].startswith('Kombi-')
print('CROSS-GAME NOT INVALIDATED / UNPRICED SGP GATE PASSED')
