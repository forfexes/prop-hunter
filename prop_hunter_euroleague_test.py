#!/usr/bin/env python3
"""Offline regression checks for EuroLeague results and persistence identity."""
from __future__ import annotations
import sys,types

stub=types.ModuleType('prop_hunter_shared_utils')
stub.http_json=lambda *a,**k:{};stub.log=lambda *a,**k:None;stub.warn=lambda *a,**k:None
stub.norm_name=lambda v:' '.join(str(v or '').lower().split())
stub.safe_json_write=lambda *a,**k:None;stub.select_pick_rows=lambda *a,**k:[]
stub.select_settlement_picks=stub.select_pick_rows
stub.to_float=lambda v,default=None: default if v in (None,'','--') else float(v)
stub.upsert_rows=lambda *a,**k:None
sys.modules['prop_hunter_shared_utils']=stub

import prop_hunter_results_euroleague as mod
import prop_hunter_card_formatter as cf

def check(value,msg):
    if not value:raise AssertionError(msg)

payload={
 'header':{'id':'401','competitions':[{'date':'2026-10-12T18:30Z'}]},
 'boxscore':{'players':[{'team':{'displayName':'Olympiacos'},'statistics':[{
  'keys':['MIN','PTS','REB','AST','3PT','STL','BLK','TO'],
  'athletes':[
   {'athlete':{'displayName':'Test Guard'},'stats':['31','24','7','11','3-6','2','0','4']},
   {'athlete':{'displayName':'Other Player'},'stats':['20','9','3','2','1-4','0','0','1']},
  ]
 }]}]}
}
rows=mod.parse_summary(payload,['Test Guard']);check(len(rows)==1,'wanted-player filtering failed');r=rows[0]
check(r['league']=='EUROLEAGUE' and r['sport']=='BASKETBALL','league normalization failed')
check(r['points']==24 and r['rebounds']==7 and r['assists']==11,'basic stats failed')
check(r['pra']==42 and r['pr']==31 and r['pa']==35 and r['ra']==18,'combo stats failed')
check(r['threes_made']==3,'3PT made-attempt parsing failed')
check(r['double_double'] is True and r['triple_double'] is False,'double/triple double failed')
check(r['season']=='2026','EuroLeague season failed')
check(mod._is_euroleague({'league':'EUROLEAGUE'}),'league detection failed')
check(mod._is_euroleague({'sport':'basketball_euroleague'}),'sport detection failed')
print('EUROLEAGUE TEST PASSED')

class P:
 type='single';player='Test Guard';market='Points Over 18.5';point=18.5;direction='over';sport='EUROLEAGUE';source_sport='EUROLEAGUE';features={'sport':'EUROLEAGUE','league':'EUROLEAGUE'}
class FakeTable:
 def __init__(self):self.updated=[]
 def update(self,payload):self.updated.append(payload);return self
 def eq(self,*a):return self
 def execute(self):return self
class FakeSB:
 def __init__(self):self.t=FakeTable()
 def table(self,*a):return self.t
class FakeModule:
 def __init__(self):
  from datetime import datetime,timezone
  self.hist=[{'date':datetime.now(timezone.utc).strftime('%Y-%m-%d'),'picks':[],'kombis':[]}];self.sb=FakeSB();self.log=types.SimpleNamespace(warning=lambda *a,**k:None)
 def dedup_key(self,player,market,point,direction):return f'{player}|{market}|{point}|{direction}'
 def persist(self,picks,*a):
  for p in picks:self.hist[0]['picks'].append({'dedup_key':self.dedup_key(p.player,p.market,p.point,p.direction),'sport':'NBA/WNBA','raw':{}})
 def load_history(self):return self.hist
 def save_history(self,h):self.hist=h
 def _get_sb(self):return self.sb
fm=FakeModule();check(cf.install_persistence(fm),'persistence install failed');fm.persist([P()])
check(fm.hist[0]['picks'][0]['sport']=='EUROLEAGUE','EuroLeague history sport repair failed')
check(fm.sb.t.updated and fm.sb.t.updated[-1].get('sport')=='EUROLEAGUE','EuroLeague DB sport repair failed')
print('EUROLEAGUE PERSISTENCE TEST PASSED')
