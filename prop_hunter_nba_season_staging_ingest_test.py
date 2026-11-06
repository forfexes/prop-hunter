import io
from prop_hunter_nba_season_staging_ingest import make_records, upload

rows = make_records("2026-27", "player_name,team,season,games_played,usage_rate\nTest Player,BOS,2026-27,12,0.25\n")
assert rows == [{"season":"2026-27","player_name":"Test Player","team":"BOS","usage_pct":25.0,"games":12,"source":"boxscorelab_csv_cc_by_4_0"}]
assert upload([], "", "") == 0
class Response:
    status=201
    def __enter__(self): return self
    def __exit__(self, *args): pass
requests=[]
def post(req, timeout):
    requests.append(req)
    return Response()
assert upload(rows, "https://example.supabase.co", "test-key", post=post) == 1
assert b'"usage_pct": 25.0' in requests[0].data
assert b'game_id' not in requests[0].data
print("NBA free season staging ingestion tests passed")
