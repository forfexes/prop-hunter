from copy import deepcopy
from prop_hunter_team_settler import match_final_score,eligible
from prop_hunter_settler import result_for_value,line_of_pick,side_of_pick
p={'player':'BYU','league':'NCAAF','market':'points Under 27.5','raw':{'game':'BYU (#10) @ TCU','commence_time':'2026-10-03T23:00:00+00:00'}}
e={'id':'401856818','date':'2026-10-03T23:00Z','status':{'type':{'completed':True}},'competitions':[{'competitors':[
 {'team':{'displayName':'TCU Horned Frogs','abbreviation':'TCU'},'score':'10'},
 {'team':{'displayName':'BYU Cougars','abbreviation':'BYU'},'score':'17'}]}]}
r=match_final_score(p,e)
assert r['actual_value']==17 and result_for_value(r['actual_value'],line_of_pick(p),side_of_pick(p))=='win'
assert match_final_score(dict(p,player='Bear Bachmeier'),e) is None
for change in ({'completed':False},{}):
 wrong=deepcopy(e);wrong['status']['type']=change;assert match_final_score(p,wrong) is None
wrong=deepcopy(e);wrong['date']='2026-10-04T23:00Z';assert match_final_score(p,wrong) is None
wrong=deepcopy(e);wrong['competitions'][0]['competitors'][0]['team']['abbreviation']='UTAH';wrong['competitions'][0]['competitors'][0]['team']['displayName']='Utah Utes';assert match_final_score(p,wrong) is None
wrong=deepcopy(e);wrong['competitions'][0]['competitors'][1]['score']=None;assert match_final_score(p,wrong) is None
assert not eligible(dict(p,market='points Under 27.5 Over 20.5'))
# Shared city is not sufficient to substitute Clippers for the quoted Lakers.
nba={'player':'Toronto Raptors','league':'NBA','market':'points Over 100.5','raw':{'game':'LA Lakers @ Toronto Raptors','commence_time':'2026-10-03T23:00Z'}}
wrong=deepcopy(e);wrong['competitions'][0]['competitors']=[{'team':{'displayName':'Los Angeles Clippers','name':'Clippers','abbreviation':'LAC'},'score':'110'},{'team':{'displayName':'Toronto Raptors','name':'Raptors','abbreviation':'TOR'},'score':'105'}]
assert match_final_score(nba,wrong) is None
assert eligible(dict(p,player='GAME')) and match_final_score(dict(p,player='GAME'),e)['actual_value']==27
print('EXACT FINAL TEAM TOTAL TEST PASSED')
