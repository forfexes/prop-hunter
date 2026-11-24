"""Hermetic automatic NBA usage tests; no network or database writes."""
import datetime as dt
from prop_hunter_nba_usage_auto import completed_games, collect, discover, existing_counts

today=dt.date(2026,11,24)
payload={"leagueSchedule":{"gameDates":[{"gameDate":"11/23/2026 00:00:00","games":[
    {"gameId":"0022600001","gameStatus":3},
    {"gameId":"0022600002","gameStatus":1},
    {"gameId":"0012600003","gameStatus":3},
    {"gameId":"0022600004","gameStatus":"3","gameDateEst":"2026-11-22T00:00:00"},
]}]}}
games=completed_games(payload,today)
assert games==[("0022600001",dt.date(2026,11,23)),("0022600004",dt.date(2026,11,22))]
assert discover(today,45,fetch=lambda url:payload)==games
posted=[]
def get(gid,day,timeout):
    assert timeout==7
    return [{"game_id":gid,"game_date":day,"player_id":123}]
def put(rows,**kw):
    posted.extend(rows)
    return len(rows)
s=collect(games,{"0022600001":20},url="https://example.supabase.co",key="fake",
          today=today,fetch_game=get,upsert=put)
assert s["attempted"]==1 and s["rows_upserted"]==1 and posted[0]["game_id"]=="0022600004"
s=collect(games,{},url="https://example.supabase.co",key="fake",today=today,
          fetch_game=lambda *a,**k:[],upsert=put)
assert s["unavailable_games"]==2 and s["rows_upserted"]==0
assert existing_counts("https://example.supabase.co","fake",today,
    fetch=lambda *a,**k:[{"nba_game_id":"0022600001","nba_player_id":1}])=={"0022600001":1}
print("AUTOMATIC NBA USAGE DISCOVERY / IDEMPOTENT BACKFILL / NO FAKE ROWS PASSED")
