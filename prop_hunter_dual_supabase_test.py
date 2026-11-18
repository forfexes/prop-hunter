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
