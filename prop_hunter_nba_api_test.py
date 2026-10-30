"""Exercise production nba_api collector without network or nba_api install."""
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
import sys
import prop_hunter_results_nba as nba

row=dict(PTS=20,REB=10,AST=11,STL=1,BLK=2,TOV=3,MIN=35,FG3M=2,
         Game_ID='nba-fixture',GAME_DATE='OCT 28, 2026',MATCHUP='SAS @ UTA')
class Frame:
    def head(self,n):return self
    def iterrows(self):return iter(enumerate([row,dict(row,MIN=0),dict(row,GAME_DATE='invalid')]))
modules={name:ModuleType(name) for name in ['nba_api','nba_api.stats','nba_api.stats.static','nba_api.stats.endpoints']}
modules['nba_api.stats.static'].players=SimpleNamespace(get_players=lambda:[dict(id=1,full_name='Stephon Castle')])
modules['nba_api.stats.endpoints'].playergamelog=SimpleNamespace(PlayerGameLog=lambda **kw:SimpleNamespace(get_data_frames=lambda:[Frame()]))
with patch.dict(sys.modules,modules):
    result=nba.nba_api_player_logs(['Stephon Castle'],season='2026-27')
assert len(result)==1
r=result[0]
assert r['game_date']=='2026-10-28' and r['pra']==41 and r['ra']==21
assert r['double_double'] is True and r['triple_double'] is True
assert r['assists']==11 and r['threes_made']==2
assert nba.nba_api_gameday('2026-10-28')=='2026-10-28'
print('NBA API COLLECTOR REGRESSION PASSED')

assert nba._event_final({'status':{'type':{'completed':True}}})
assert not nba._event_final({'status':{'type':{'completed':False,'state':'in'}}})
assert not nba._event_final({})
assert not nba._event_final({'status':{'type':{'completed':False,'state':'post'}}})
seen=[]
events=[{'id':'live','status':{'type':{'completed':False,'state':'in'}}},
        {'id':'unknown'}, {'id':'final','status':{'type':{'completed':True,'state':'post'}}}]
with patch.object(nba,'espn_scoreboard',return_value=events),patch.object(nba,'_event_matches',return_value=True),patch.object(nba,'espn_summary_players',side_effect=lambda gid,names:seen.append(gid) or []):
    nba.espn_pending_logs([dict(player='Stephon Castle',sport='NBA',date='2026-10-29')])
assert seen==['final'],seen
print('NBA FINAL BOXSCORE COLLECTION GUARD PASSED')
