"""Offline check: only snapshot tables use secondary; picks and gamelogs stay primary."""
import os
from unittest.mock import patch
import prop_hunter_shared_utils as u

class Client:
    def __init__(self, label): self.label=label
created=[]
def factory(url,key):
    created.append((url,key))
    return Client(url)

with patch.object(u,"create_client",side_effect=factory):
    with patch.dict(os.environ,{
        "SUPABASE_URL":"https://primary.example","SUPABASE_KEY":"primary-test-key",
        "SUPABASE_SECONDARY_URL":"https://secondary.example",
        "SUPABASE_SECONDARY_SERVICE_ROLE_KEY":"secondary-test-key",
    }):
        assert u.table_supabase_client("prop_hunter_prop_snapshots").label=="https://secondary.example"
        assert u.table_supabase_client("prop_hunter_picks").label=="https://primary.example"
        assert u.table_supabase_client("prop_hunter_player_gamelogs").label=="https://primary.example"
        assert u.table_supabase_client("prop_hunter_results").label=="https://primary.example"
        assert created[0]==("https://secondary.example","secondary-test-key")
        assert created[1]==("https://primary.example","primary-test-key")
    with patch.dict(os.environ,{
        "SUPABASE_URL":"https://primary.example","SUPABASE_KEY":"primary-test-key",
        "SUPABASE_SECONDARY_URL":"","SUPABASE_SECONDARY_SERVICE_ROLE_KEY":""
    }):
        assert u.table_supabase_client("prop_hunter_prop_snapshots") is None
        assert u.table_supabase_client("prop_hunter_picks").label=="https://primary.example"
print("SUPABASE TWO-PROJECT ROUTING: PASS")

# Regression: bookmaker event times sometimes arrive as Unix seconds/milliseconds.
from datetime import datetime, timezone
stamp=1794972600
iso=datetime.fromtimestamp(stamp,timezone.utc).isoformat()
clean=u._snapshot_temporal_fields({
    "commence_time":str(stamp),
    "snapshot_ts":stamp*1000,
    "game_date":str(stamp),
    "date":stamp,
    "created_at":"2026-11-18T02:00:00+00:00",
    "raw":{"original_timestamp":stamp},
})
assert clean["commence_time"]==iso
assert clean["snapshot_ts"]==iso
assert clean["game_date"]==iso[:10]
assert clean["date"]==iso[:10]
assert clean["created_at"]=="2026-11-18T02:00:00+00:00"
assert clean["raw"]=={"original_timestamp":stamp}
print("SUPABASE SNAPSHOT UNIX TIMESTAMP NORMALIZATION: PASS")
