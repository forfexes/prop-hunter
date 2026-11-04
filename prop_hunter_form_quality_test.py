from types import SimpleNamespace as Obj
from copy import deepcopy
from prop_hunter_form_quality import profile,rejection,filter_tickets
from prop_hunter_builder_engine import _candidate_probability,_ladder_leg_candidate

def feat(vals,line=9.5,side='over'):
 return dict(gamelog_n=len(vals),gamelog_l15_n=len(vals),gamelog_l15_hits=sum(v>line if side=='over' else v<line for v in vals),gamelog_l15_line=line,gamelog_l15_direction=side,recent_form=profile(vals,line,side),odds_observed=True,price_type='bookmaker',gamelog_model_rate=.8)
# Equal overall counts can conceal a recent collapse. Test chronological order.
bad=feat([0]*5+[20]*10);good=feat([20]*10+[0]*5)
assert rejection(bad,9.5,'over')=='recent_form_deterioration'
assert rejection(good,9.5,'over') is None
assert rejection(feat([20]*5+[0]*10,side='under'),9.5,'under')=='recent_form_deterioration'
assert profile([1]*7,1,'under')['l5']['hits']==0, 'pushes are not under hits'
assert rejection(feat([20]*5),9.5,'over')=='insufficient_current_games'
assert rejection(good,10.5,'over')=='mismatched_form_line'
assert rejection(good,9.5,'under')=='mismatched_form_side'
p=Obj(features=good,odds=2.2,player='Test',market='points',point=9.5,direction='over',sport='NBA',game='A @ B')
assert _candidate_probability(p)==.8, 'real gamelog estimate did not reach builder'
p.features=bad;assert _candidate_probability(p) is None
p.features=good;p.point=10.5;assert _candidate_probability(p) is None
p.point=9.5
single=Obj(type='single',point=9.5,direction='over',features=good)
bad_single=Obj(type='single',point=9.5,direction='over',features=bad)
leg=dict(point=9.5,direction='over',features=good)
combo=Obj(type='big',leg_details=[leg,deepcopy(leg)])
ladder=Obj(type='ladder',leg_details=[leg,deepcopy(leg)])
bad_combo=Obj(type='big',leg_details=[leg,dict(leg,features=bad)])
assert filter_tickets([single,bad_single,combo,ladder,bad_combo])[0]==[single,combo,ladder]
# Existing Wilson test still constrains actual rung probability.
p.features=feat([20]*15);p.point=9.5
candidate=_ladder_leg_candidate(p)
assert candidate and candidate['probability']<=.8
print('RECENT FORM / EXACT LINE / BUILDER MODEL WIRING / ALL-TICKET DELIVERY GUARDS PASSED')

binary=feat([0]*5+[1]*10,line=.5);binary['gamelog_dd_rate']=2/3
assert rejection(binary,None,'yes')=='recent_form_deterioration'
print('BINARY DD/TD FORM GUARD PASSED')
