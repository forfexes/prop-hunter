#!/usr/bin/env python3
from pathlib import Path
from prop_hunter_settler import build_log_index, find_gamelog

logs=[]
for i in range(2000):
    logs.append({
        "id": i+1,
        "player_name": f"Noise Player {i}",
        "normalized_name": f"noise player {i}",
        "game_id": f"noise-{i}",
        "game_date": "2026-10-01",
    })
logs.append({
    "id": 3001,
    "player_name": "Exact Player",
    "normalized_name": "exact player",
    "game_id": "game-123",
    "game_date": "2026-10-02",
    "points": 21,
})
idx=build_log_index(logs)
pick={"player":"Exact Player","game_id":"game-123","date":"2026-10-02"}
gl=find_gamelog(pick,logs,aliases={},log_index=idx)
assert gl and gl["game_id"]=="game-123", gl
assert len(idx["exact player"])==1

source=Path("prop_hunter_settler.py").read_text(encoding="utf-8")
assert 'def _load_relevant_gamelogs' in source
assert '.in_("normalized_name", batch)' in source
assert '.gte("game_date", start.isoformat())' in source
assert '.lte("game_date", end.isoformat())' in source
assert 'logs = _load_relevant_gamelogs(picks)' in source
print("SETTLER FAST INDEX TEST PASSED")


# Future-date gamelogs must never settle a current pick.
future_logs=[{
    "id":4001,
    "player_name":"Exact Player",
    "normalized_name":"exact player",
    "game_id":"future-game",
    "game_date":"2026-10-04",
    "points":33,
}]
future_pick={
    "player":"Exact Player",
    "date":"2026-10-02",
    "commence_time":"2026-10-02T20:00:00+00:00",
}
assert find_gamelog(future_pick,future_logs,aliases={},log_index=build_log_index(future_logs)) is None

from prop_hunter_shared_utils import pick_id
a={"id":96,"date":"2026-10-21","dedup_key":"same|market|0.5|under","event_id":"event-a","bookmaker":"book"}
b={"id":96,"date":"2026-10-06","dedup_key":"same|market|0.5|under","event_id":"event-b","bookmaker":"book"}
assert pick_id(a) != pick_id(b), (pick_id(a), pick_id(b))
print("SETTLEMENT IDENTITY/DATE GUARDS PASSED")

from prop_hunter_settler import detect_stat
assert detect_stat("rushing_attempts Over 5.5") == "rushing_attempts"
assert detect_stat("Rushing Attempts Over 9.5") == "rushing_attempts"
# UTC Friday kickoff can be the previous official US gameday in nflverse.
nfl_logs=[{"player_name":"Cole Kmet","normalized_name":"cole kmet","game_id":"2026_08_NE_CHI","game_date":"2026-10-22","receptions":4}]
nfl_pick={"player":"Cole Kmet","league":"NFL","market":"receptions Over 1.5","commence_time":"2026-10-23T00:15:00Z"}
assert find_gamelog(nfl_pick,nfl_logs,aliases={},log_index=build_log_index(nfl_logs)) is not None
print("NFL SETTLEMENT MARKET/LOCAL-DATE TEST PASSED")

# Official NHL goalie logs omit saves but retain exact shots/goals against.
from prop_hunter_results_nhl import goalie_saves, logs_for
from prop_hunter_settler import stat_value
from unittest.mock import patch
for raw, expected in [({'shotsAgainst':26,'goalsAgainst':1},25),
                      ({'shotsAgainst':0,'goalsAgainst':0},0),
                      ({'shotsAgainst':26},None),
                      ({'shotsAgainst':2,'goalsAgainst':3},None),
                      ({'shotsAgainst':2.5,'goalsAgainst':1},None),
                      ({'saves':0,'shotsAgainst':26,'goalsAgainst':1},0)]:
    assert goalie_saves(raw) == expected
    assert stat_value({'league':'NHL','source':'nhl_official_api','raw':raw}, 'goalie_saves') == expected
assert stat_value({'league':'NBA','source':'nhl_official_api','raw':{'shotsAgainst':26,'goalsAgainst':1}},'goalie_saves') is None
with patch('prop_hunter_results_nhl.player_id', return_value=1), patch('prop_hunter_results_nhl.http_json', return_value={'gameLog':[{'gameId':2026020196,'gameDate':'2026-10-27','shotsAgainst':26,'goalsAgainst':1}]}):
    assert logs_for('Adin Hill')[0]['goalie_saves'] == 25
print('OFFICIAL NHL GOALIE SAVES TEST PASSED')

from prop_hunter_results_nfl import kicking_stats
assert kicking_stats({'position':'K','fg_made':2,'pat_made':1})['kicking_points'] == 7
assert kicking_stats({'position':'K','fg_made':0,'pat_made':0})['kicking_points'] == 0
assert kicking_stats({'position':'K','fg_made':2})['kicking_points'] is None
assert kicking_stats({'position':'WR','fg_made':2,'pat_made':1}) == {}
assert stat_value({'league':'NFL','raw':{'position':'K','fg_made':0,'pat_made':1}}, 'points') == 1
assert stat_value({'league':'NFL','raw':{'position':'WR','fg_made':0,'pat_made':1}}, 'points') is None
print('NFL OBSERVED KICKER SCORING TEST PASSED')

# Row budget applies to wanted output, never to the league-wide input frame.
import sys, types, os
from prop_hunter_results_nfl import nflreadpy_weekly
class WeeklyFixture:
    def iterrows(self):
        for i in range(6):
            yield i, {'player_display_name':'Unrequested Player','season':2026,'week':1,'team':'NO'}
        for week in (6,7,8):
            yield week + 10, {'player_display_name':'Joey Slye','season':2026,'week':week,'team':'TEN','position':'K','fg_made':2,'pat_made':1}
fixture_nfl = types.SimpleNamespace(load_player_stats=lambda **kw:WeeklyFixture())
schedules = {('2026',str(w),'TEN'):{'game_id':f'2026_{w}_TEN_OPP','game_date':f'2026-10-{w:02}'} for w in (6,7,8)}
with patch.dict(sys.modules, {'nflreadpy':fixture_nfl}), patch('prop_hunter_results_nfl._schedule_map',return_value=schedules), patch.dict(os.environ,{'NFL_RESULT_ROW_CAP':'2'}):
    late = nflreadpy_weekly([2026], ['Joey Slye'])
    assert [r['week'] for r in late] == ['6','7'], late
    assert all(r['kicking_points'] == 7 and r['game_date'] for r in late)
print('NFL LATE-WEEK ROW BUDGET TEST PASSED')
