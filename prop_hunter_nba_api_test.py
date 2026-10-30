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
