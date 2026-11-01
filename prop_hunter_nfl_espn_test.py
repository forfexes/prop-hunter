from copy import deepcopy
from prop_hunter_nfl_espn import collect,summary_rows
E={'id':'123','date':'2026-10-30T00:15:00Z','status':{'type':{'completed':True,'state':'post'}}}
S={'header':{'id':'123','competitions':[deepcopy(E)]},'boxscore':{'players':[{'team':{'abbreviation':'BUF'},'statistics':[
 {'name':'passing','labels':['C/ATT','YDS','TD','INT'],'athletes':[{'athlete':{'id':'17','displayName':'Josh Allen'},'stats':['20/30','250','2','0']}]},
 {'name':'rushing','labels':['CAR','YDS','TD'],'athletes':[{'athlete':{'id':'17','displayName':'Josh Allen'},'stats':['8','40','1']}]},
 {'name':'receiving','labels':['REC','YDS','TD','TGTS'],'athletes':[{'athlete':{'id':'17','displayName':'Josh Allen'},'stats':['1','5','0','1']}]}]}]}}
r=summary_rows(S,E,{'josh allen'});assert len(r)==1
assert r[0]['passing_yards']==250 and r[0]['receiving_yards']==5 and r[0]['touchdowns']==1
assert r[0]['game_date']=='2026-10-29' and r[0]['raw']['athlete_id']=='17'
x=deepcopy(S);x['boxscore']['players'][0]['statistics'].pop()
r=summary_rows(x,E,{'josh allen'})[0];assert 'touchdowns' not in r
x=deepcopy(S);x['header']['competitions'][0]['status']['type']['completed']=False
assert not summary_rows(x,E,{'josh allen'})
x=deepcopy(S);x['boxscore']['players'][0]['statistics'][0]['athletes'].append({'athlete':{'id':'99','displayName':'Josh Allen'},'stats':['1/2','20','0','0']})
assert not summary_rows(x,E,{'josh allen'}), 'duplicate identity must fail closed'
x=deepcopy(S)
for g in x['boxscore']['players'][0]['statistics']:g['athletes'][0]['didNotPlay']=True
assert not summary_rows(x,E,{'josh allen'})
x=deepcopy(S);x['header']['id']='other';assert not summary_rows(x,E,{'josh allen'})
p=dict(player='Josh Allen',league='NFL',status='pending',commence_time='2026-10-30T00:15:00Z')
calls=[]
def get(url,params):
 calls.append((url,params))
 return deepcopy(S) if url.endswith('summary') else {'events':[deepcopy(E)]}
assert len(collect([p],[],get))==1
assert len([u for u,p in calls if u.endswith('summary')])==1
assert not collect([p],[dict(player_name='Josh Allen',game_date='2026-10-29')],get)
live=deepcopy(E);live['status']['type']['state']='in';live['status']['type']['completed']=False
assert not collect([p],[],lambda url,params:{'events':[live]})
assert not collect([dict(p,commence_time='2026-10-31T00:15:00Z')],[],get)
assert not collect([dict(p,status='win')],[],get)
try:collect([p],[],lambda url,params:None)
except RuntimeError:pass
else:raise AssertionError('fetch failure must remain visible')
print('NFL ESPN FINAL / IDENTITY / CATEGORY MERGE / NATIVE PRESERVATION PASSED')

# Several NFL games share a kickoff. A game hint must disambiguate them.
from prop_hunter_nfl_espn import event_matches
team_event=deepcopy(E)
team_event['competitions']=[{'competitors':[{'team':{'displayName':'Buffalo Bills','abbreviation':'BUF','name':'Bills'}},{'team':{'displayName':'Miami Dolphins','abbreviation':'MIA','name':'Dolphins'}}]}]
assert event_matches(team_event,dict(p,game='BUF Bills @ MIA Dolphins'))
assert not event_matches(team_event,dict(p,game='Seattle Seahawks @ Arizona Cardinals'))
other=deepcopy(E);other['id']='999'
assert not collect([p],[],lambda url,params:{'events':[E,other]}), 'same-time ambiguous event must not be guessed'
x=deepcopy(S);x['boxscore']['players'][0]['statistics'][0]['athletes'][0]['stats'][1]='--'
assert 'passing_yards' not in summary_rows(x,E,{'josh allen'})[0]
print('NFL SAME-KICKOFF EVENT DISAMBIGUATION / MISSING VALUE GUARDS PASSED')
