#!/usr/bin/env python3
from datetime import datetime, timezone
from prop_hunter_snapshot_retention import cutoff_iso

cutoff = datetime.fromisoformat(cutoff_iso(7))
now = datetime.now(timezone.utc)
delta = now - cutoff
assert 6.99 < delta.total_seconds() / 86400 < 7.01, delta
print("SNAPSHOT RETENTION TEST PASSED")
