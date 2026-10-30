from datetime import date,timedelta,datetime,timezone
from prop_hunter_scan_dates import select_scan_dates
base=date(2026,10,30)
old={(base-timedelta(days=i)).strftime('%Y%m%d'):[i] for i in range(20,50)}
current={d.strftime('%Y%m%d'):[1] for d in [base-timedelta(days=1),base,base+timedelta(days=1)]}
data=dict(old,**current)
selected=select_scan_dates(data,18,base)
keys=[k for k,_ in selected]
assert len(keys)==18 and len(set(keys))==18
assert '20261029' in keys and '20261030' in keys
assert '20261031' not in keys
assert all(value==data[key] for key,value in selected)
seen=set()
for i in range(len(old)):
    seen.update(k for k,_ in select_scan_dates(old,5,base+timedelta(days=i)))
assert seen==set(old), 'historical rotation starves a date'
assert len(select_scan_dates(data,5,base))==5
assert select_scan_dates({'bad':[]},5,base)==[]
assert list(data)==list(dict(old,**current)), 'input changed'
# Exercise actual WNBA main with 30 old dates ahead of the completed current game.
from unittest.mock import patch
import prop_hunter_results_wnba as wnba
picks=[dict(player='P',sport='WNBA',date=(base-timedelta(days=i)).isoformat()) for i in range(20,50)]
picks.append(dict(player='Jordin Canada',sport='WNBA',date='2026-10-29'))
scanned=[]
class Clock(datetime):
    @classmethod
    def now(cls,tz=None): return datetime(2026,10,30,tzinfo=timezone.utc)
with patch.object(wnba,'pending_picks',return_value=picks), patch.object(wnba,'espn_scoreboard',side_effect=lambda day:scanned.append(day) or []), patch.object(wnba,'safe_json_write'), patch.object(wnba,'datetime',Clock):
    wnba.main()
assert '20261029' in scanned and len(scanned)<=18
print('SCOREBOARD DATE FAIRNESS REGRESSIONS PASSED')
