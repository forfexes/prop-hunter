from prop_hunter_nba_usage_ingest import upsert_official_game_usage
import json
captured=[]
def fake_post(req):
    captured.append(req)
row={"player_id":123,"game_id":"0022600001","game_date":"2026-10-28",
     "usage_pct":27.2,"source":"nba_official_boxscore_usage_v3","scope":"game"}
assert upsert_official_game_usage([],url="",service_key="")==0
assert upsert_official_game_usage([row],url="https://example.supabase.co",service_key="fake",post=fake_post)==1
assert json.loads(captured[0].data)[0]["nba_player_id"]==123
assert "on_conflict=nba_player_id,nba_game_id" in captured[0].full_url
for bad in ({**row,"scope":"season"},{**row,"usage_pct":110},{**row,"game_id":"bad"}):
    try:
        upsert_official_game_usage([bad],url="https://example.supabase.co",service_key="fake",post=fake_post)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid observation accepted")
print("NBA USAGE SUPABASE INGEST CONTRACT PASSED")
