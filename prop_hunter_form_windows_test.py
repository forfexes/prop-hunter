import ast,logging,os,re
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from prop_hunter_form_windows import select_form_rows,form_context,season_floor

current=[dict(normalized_name='fixture',player_name='Fixture',league='NBA',sport='BASKETBALL',season='2026-27',game_id=f'n{i}',game_date=f'2026-10-{27-i:02}',rebounds=x) for i,x in enumerate([3,10,9,6,5,4,8])]
old=[dict(current[0],game_id=f'o{i}',game_date=f'2026-04-{20-i:02}',rebounds=19) for i in range(8)]
other=[dict(r,league='WNBA',rebounds=25) for r in current]
future=[dict(current[0],game_date='2026-11-01',rebounds=99)]
rows=current+old+other+future
assert select_form_rows(rows,'NBA','2026-10-30')==current
assert form_context(rows,'NBA','2026-10-30')['form_games_available']==7
assert season_floor('NBA','2027-01-01')==date(2026,9,1)
assert season_floor('NFL','2027-01-01')==date(2026,7,1)
assert season_floor('MLB','2026-10-30')==date(2026,1,1)
assert select_form_rows([dict(current[0],game_date=None)],'NBA','2026-10-30')==[]

verified=dict(current[0],raw={'start_time_utc':'2026-10-27T01:00Z'})
wrong=dict(current[0],game_id='conflict',rebounds=99)
assert select_form_rows([verified,wrong],'NBA','2026-10-30')==[verified]
assert select_form_rows([current[0],wrong],'NBA','2026-10-30')==[]
assert len(select_form_rows([current[0],dict(current[0],game_id='duplicate')],'NBA','2026-10-30'))==1

# Execute the production enrichment, including its fallback query and cache.
tree=ast.parse(Path('prophunter_core_1391.py').read_text())
fn=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='enrich_gamelogs_fairprob')
class Query:
    @property
    def not_(self):return self
    def table(self,*a):return self
    def select(self,*a):return self
    def in_(self,*a):
        if fallback:raise RuntimeError('batch unavailable')
        return self
    def eq(self,*a):return self
    def is_(self,*a):return self
    def order(self,*a,**kw):return self
    def limit(self,*a):return self
    def execute(self):return SimpleNamespace(data=active_rows)
ns=dict(_sb_read=lambda:Query(),_GAMELOG_CACHE={},norm_name=lambda x:'fixture',
        log=logging.getLogger('form'),os=os,re=re,datetime=datetime,timezone=timezone)
exec(compile(ast.Module(body=[fn],type_ignores=[]),'production-form','exec'),ns)
def prop(sport='NBA',fair=None):
    return SimpleNamespace(player='Fixture',market='Rebounds',sport=sport,point=13.5,odds=12,
        direction='over',commence_time='2026-10-30T02:00Z',enrichment='src:fanduel',
        features={} if fair is None else {'fair_prob':fair})
for fallback in [False,True]:
    active_rows=rows;ns['_GAMELOG_CACHE'].clear()
    a,b=prop(),prop('WNBA')
    ns['enrich_gamelogs_fairprob']([a,b])
    assert a.features['gamelog_l15_n']==7 and a.features['gamelog_l15_hits']==0
    assert b.features['gamelog_l15_n']==7 and b.features['gamelog_l15_hits']==7
    active_rows=current[:3]+old;ns['_GAMELOG_CACHE'].clear()
    a,b=prop(),prop(fair=.2)
    ns['enrich_gamelogs_fairprob']([a,b])
    assert a.features['gamelog_n']==3 and 'fair_prob' not in a.features
    assert b.features['fair_prob']==.2

# Equal-to-line outcomes are pushes, not successful Under observations.
fallback=False
active_rows=[dict(r,rebounds=10) for r in current];ns['_GAMELOG_CACHE'].clear()
push=prop();push.point=10;push.direction='under'
ns['enrich_gamelogs_fairprob']([push])
assert push.features['gamelog_l15_hits']==0
assert push.features['gamelog_l15_rate']==0, push.features
assert push.features['gamelog_l10_rate']==0

active_rows=[dict(current[0],game_id=f'l{i}',game_date=(date(2026,10,27)-timedelta(days=i)).isoformat(),rebounds=0 if i<10 else 20) for i in range(15)]
ns['_GAMELOG_CACHE'].clear()
long=prop()
ns['enrich_gamelogs_fairprob']([long])
assert long.features['gamelog_l10_n']==10 and long.features['gamelog_l10_hits']==0
assert long.features['gamelog_l15_n']==15 and long.features['gamelog_l15_hits']==5
assert long.features['gamelog_l10_rate']==0 and long.features['gamelog_l15_rate']==.333

# Feature rebuild preserves the older comparison but reports current count.
import prop_hunter_feature_builder as fb
import prop_hunter_form_windows as fw
class Clock(datetime):
    @classmethod
    def now(cls,tz=None):return datetime(2026,10,30,tzinfo=timezone.utc)
saved=[]
with patch.object(fw,'datetime',Clock),patch.object(fb,'select_rows',return_value=current+old),patch.object(fb,'safe_json_write'),patch.object(fb,'upsert_rows',side_effect=lambda table,batch,key:saved.extend(batch)):
    fb.main()
assert saved[0]['games_total']==7
assert saved[0]['features']['retained_games_total']==15
assert saved[0]['features']['last_15']['rebounds_avg']==round(sum(x['rebounds'] for x in current)/7,4)
assert 'historical_last_15' in saved[0]['features']
print('CURRENT SEASON FORM / NO FABRICATED EDGE REGRESSIONS PASSED')
