"""Reject fabricated/expired mixed quotes and grade explicit final team markets."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace as N
from prop_hunter_mixed_builders import build,team_leg_valid
from prop_hunter_team_settler import match_final_score
from prop_hunter_form_quality import filter_tickets
from prop_hunter_combo_prices import publishable_extra
now=datetime(2026,11,5,12,tzinfo=timezone.utc);start=(now+timedelta(hours=8)).isoformat()
f={'gamelog_n':15,'gamelog_l15_line':20.5,'gamelog_l15_direction':'over','bookmaker':'book'}
prop=N(player='A Player',market='Points',point=20.5,direction='over',odds=1.9,game='Lakers @ Celtics',sport='NBA',event_id='event',commence_time=start,features=f)
team={'kind':'team','selection_id':'team','player':'Lakers','market':'Moneyline','point':.5,'direction':'over','odds':1.8,'raw':{'team_builder_market':'moneyline','tie_rule':'push','scope':'full_game_including_ot'}}
pl={'kind':'player','selection_id':'player','player':'A Player','market':'Points','point':20.5,'direction':'over','odds':1.9}
q={'quote_id':'q1','odds_observed':True,'event_id':'event','bookmaker':'book','sport':'NBA','game':prop.game,'commence_time':start,'observed_at':now.isoformat(),'expires_at':(now+timedelta(minutes=10)).isoformat(),'odds':3.0,'legs':[team,pl]}
f['confirmed_builder_quotes']=[q]
picks=build([prop],N,now);assert len(picks)==1
assert picks[0].odds==3 and picks[0].probability is None and picks[0].ev is None
assert publishable_extra(picks[0]) and filter_tickets(picks)[0]==picks
for key,value in [('odds_observed',False),('bookmaker','wrong'),('expires_at',now.isoformat()),('odds',float('nan')),('observed_at',(now-timedelta(hours=2)).isoformat())]:
 wrong=deepcopy(q);wrong[key]=value;f['confirmed_builder_quotes']=[wrong];assert not build([prop],N,now),(key,value)
for change in ({'player':'Wrong Player'},{'point':21.5},{'selection_id':'team'}):
 wrong=deepcopy(q);wrong['legs'][1].update(change);f['confirmed_builder_quotes']=[wrong];assert not build([prop],N,now)
leg=picks[0].leg_details[0]
event={'id':'espn-event','date':start,'status':{'type':{'completed':True}},'competitions':[{'competitors':[{'team':{'name':'Lakers'},'score':'110'},{'team':{'name':'Celtics'},'score':'105'}]}]}
assert match_final_score(leg,event)['actual_value']==1
wrong=deepcopy(event);wrong['competitions'][0]['competitors'][0]['score']='100';assert match_final_score(leg,wrong)['actual_value']==0
wrong['competitions'][0]['competitors'][0]['score']='105';assert match_final_score(leg,wrong)['actual_value']==.5
both=deepcopy(leg);both['raw']['team_builder_market']='both_over';both['point']=100;both['player']='GAME'
assert match_final_score(both,event)['actual_value']==105
both['raw']['scope']='first_half';assert not team_leg_valid(both) and match_final_score(both,event) is None
wrong=deepcopy(event);wrong['status']['type']['completed']=False;assert match_final_score(leg,wrong) is None
print('MIXED BUILDER TEST PASSED: observed prices, form, expiry, selection identity, moneyline, both-over, final scope')

# End-to-end result indexing uses the preserved book event and grades all legs.
from unittest.mock import patch
import prophunter_results as reporter
combo=vars(picks[0]).copy()
rows=[]
for index,l in enumerate(combo['leg_details']):
 rows.append({'result':'win','actual_value':1 if index==0 else 25,'pick_raw':dict(l)})
with patch.object(reporter,'_settlement_ready_time',return_value=True):
 by_dedup,by_signature=reporter._index_results(rows)
 assert reporter._settle_combo(combo,by_dedup,by_signature)
 assert combo['result']=='win' and abs(combo['profit']-.1)<1e-8
 assert all(l['result']=='win' for l in combo['leg_details'])
assert all(len(l['selection_id'])==64 for l in picks[0].leg_details)
print('MIXED BUILDER RESULT INDEX / COMBINED PRICE PROFIT TEST PASSED')
