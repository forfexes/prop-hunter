from copy import deepcopy
from unittest.mock import patch
import prophunter_results as r
from prop_hunter_quote_guard import canonical_market
from prop_hunter_pending_audit import classify

known=dict(player='Known Player',market='Threes Over 5.5',point=5.5,direction='over',sport='NBA',game='A @ B',event_id='book-event',commence_time='2026-11-04T23:00Z',date='2026-11-04')
unknown=dict(player='Unknown Player',market='First 3 Minutes Threes Over 0',point=0,direction='over',sport='NBA',game='C @ D',date='2026-11-04')
result=dict(result='loss',actual_value=1,game_id='official-event',result_id='r1',pick_raw=known)
base=dict(type='big',result='pending',stake=.05,odds=100,date='2026-11-04',leg_details=[unknown,known])
with patch.object(r,'_settlement_ready_time',return_value=True):
 idx=r._index_results([result])
 for legs in ([unknown,known],[known,unknown]):
  c=dict(base,leg_details=deepcopy(legs));assert r._settle_combo(c,*idx)
  assert c['result']=='loss' and c['profit']==-.05 and c['settlement_decisive_leg']['actual_value']==1
  assert not r._settle_combo(c,*idx),'not idempotent'
  assert any(x.get('result') is None for x in c['settlement_legs']),'invented unknown result'
 c=dict(base,type='ladder');assert not r._settle_combo(c,*idx) and c['result']=='pending'
 for modified in (dict(result,result='win'),dict(result,pick_raw=dict(known,commence_time='2026-11-03T23:00Z')),dict(result,pick_raw=dict(known,event_id='different-event',game='Other @ Fixture')),dict(result,actual_value=None)):
  c=deepcopy(base);assert not r._settle_combo(c,*r._index_results([modified]));assert c['result']=='pending'
 for typ in ('big','super','lottery','kombi2','kombi3'):
  p=dict(base,pick_type=typ,market='3-Leg LOTTERY',player='A + B',league='?',leg_details=[known,unknown])
  with patch('prop_hunter_pending_audit._pick_ready_for_settlement',return_value=True):assert classify(p,[],{})=='awaiting_combo_legs'
assert canonical_market('Player To Record A Three In The First 3 Minutes Over 0')=='unsupported_period'
assert canonical_market('threes','First Minutes')=='unsupported_period'
assert canonical_market('Threes Over 1.5')=='threes'
print('DECISIVE LOSS / UNKNOWN LEG / LADDER / IDENTITY / TIMED MARKET TEST PASSED')
