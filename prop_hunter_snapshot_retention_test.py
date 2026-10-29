#!/usr/bin/env python3
from datetime import datetime, timezone
from prop_hunter_snapshot_retention import cutoff_iso

cutoff = datetime.fromisoformat(cutoff_iso(7))
now = datetime.now(timezone.utc)
delta = now - cutoff
assert 6.99 < delta.total_seconds() / 86400 < 7.01, delta
print("SNAPSHOT RETENTION TEST PASSED")

from unittest.mock import MagicMock, patch
from prop_hunter_snapshot_retention import apply_retention, TABLE
sb=MagicMock()
query=sb.table.return_value
query.select.return_value.lt.return_value.limit.return_value.execute.side_effect=[
    MagicMock(data=[{'snapshot_id':'old-a'},{'snapshot_id':'old-b'}]), MagicMock(data=[])]
with patch('prop_hunter_snapshot_retention.supabase_client',return_value=sb):
    assert apply_retention(7,batch_size=2)==2
assert query.delete.return_value.in_.call_args.args == ('snapshot_id',['old-a','old-b'])
assert query.delete.return_value.in_.return_value.lt.call_args.args[0]=='created_at'
assert all(c.args==(TABLE,) for c in sb.table.call_args_list)
# Propagate write errors; never silently report successful retention.
query.select.return_value.lt.return_value.limit.return_value.execute.side_effect=[MagicMock(data=[{'snapshot_id':'old'}])]
query.delete.return_value.in_.return_value.lt.return_value.execute.side_effect=RuntimeError('write failed')
with patch('prop_hunter_snapshot_retention.supabase_client',return_value=sb):
    try: apply_retention()
    except RuntimeError: pass
    else: raise AssertionError('retention write failure swallowed')
print('BOUNDED SNAPSHOT RETENTION TEST PASSED')

# A permanent backlog cannot turn a bounded maintenance job into an endless loop.
sb=MagicMock();q=sb.table.return_value
q.select.return_value.lt.return_value.limit.return_value.execute.return_value.data=[{'snapshot_id':'old'}]
with patch('prop_hunter_snapshot_retention.supabase_client',return_value=sb):
    assert apply_retention(max_batches=2)==2
assert q.delete.call_count==2
