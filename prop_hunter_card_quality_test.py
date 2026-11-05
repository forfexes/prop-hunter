from types import SimpleNamespace as N
from unittest.mock import patch
from copy import deepcopy
import prop_hunter_image_cards as cards
from prop_hunter_form_quality import filter_singles,filter_tickets,price_sample_rejection
from prop_hunter_quote_incidents import invalidate
from prophunter_results import _decorate_card,_performance_rows
from prop_hunter_builder_engine import build_autonomous_extras
f={'gamelog_n':6,'gamelog_l15_n':6,'gamelog_l15_line':1.5,'gamelog_l15_direction':'over'}
p=N(type='single',player='Parker Washington',market='2_plus_td',point=1.5,direction='over',odds=14,features=f)
assert filter_singles([p])[0]==[]
assert price_sample_rejection(dict(f,gamelog_n=10,gamelog_l15_n=10),14) is None
assert price_sample_rejection(dict(f,gamelog_n=15,gamelog_l15_n=6),14)=='longshot_insufficient_form'
assert price_sample_rejection(f,9.99) is None
assert filter_tickets([N(type='big',leg_details=[dict(odds=14,features=f,point=1.5,direction='over')]*2)])[0]==[]
assert cards._label({'market':'2_plus_td Over 1.5','point':1.5,'direction':'over'})=='2+ Touchdowns'
with patch.object(cards,'_get_json',return_value={'sports':[{'leagues':[{'teams':[{'team':{'name':'Jaguars','abbreviation':'JAX','displayName':'Jacksonville Jaguars','logos':[{'href':'verified-logo'}]}}]}]}]}),patch.object(cards,'_get_image',side_effect=lambda url:url):
 cards._CACHE.clear();assert cards.team_logo('JAX Jaguars',('football','nfl'))=='verified-logo'
 assert cards.team_logo('JAX Ravens',('football','nfl')) is None
 cards._CACHE['teams:nfl']=[{'names':{'duplicate'},'logo':'a'},{'names':{'duplicate'},'logo':'b'}]
 assert cards.team_logo('duplicate',('football','nfl')) is None
p=dict(player='Parker Washington',market='2_plus_td Over 1.5',odds=14,features=f,result='pending',dedup_key='p')
assert invalidate(p,'2026-11-05') and p['quality_invalidated'] and not p.get('quote_invalidated')
assert p['result']=='withdrawn' and p['profit'] is None and not invalidate(p,'2026-11-05')
assert not _performance_rows([{'picks':[p]}])
c=dict(text='Parker Washington\n• 2+ Touchdowns @14\n📈 Prob 20%\n🏁 Auswertung: offen',pick_keys=['p'])
text=_decorate_card(c,[p],[]);assert 'mindestens 10' in text and '20%' not in text
# Independently qualified ladders must survive an empty combination pool.
ladder=N(type='ladder',picks=[],legs=[],features={})
with patch('prop_hunter_builder_engine._real_ladders',return_value=[ladder]):assert build_autonomous_extras([],[],N,N)==[ladder]
print('FINAL LONGSHOT GATE / TOUCHDOWN LABEL / VERIFIED LOGO ALIASES / QUALITY WITHDRAWAL / LADDER INDEPENDENCE PASSED')
