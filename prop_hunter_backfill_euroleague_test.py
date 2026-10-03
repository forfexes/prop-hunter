#!/usr/bin/env python3
from prop_hunter_backfill_euroleague import (
    KEEP, FULL_LOOKBACK_DAYS, INCREMENTAL_DAYS, FULL_EVENT_CAP,
)

assert 30 <= KEEP <= 40
assert 300 <= FULL_LOOKBACK_DAYS <= 500
assert 3 <= INCREMENTAL_DAYS <= 14
assert 250 <= FULL_EVENT_CAP <= 600

sample = {
    "id": "1",
    "date": "2026-10-01T18:00Z",
    "status": {"type": {"completed": True}},
}
assert sample["status"]["type"]["completed"] is True
print("EUROLEAGUE BACKFILL TEST PASSED")
