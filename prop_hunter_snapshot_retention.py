#!/usr/bin/env python3
"""Delete stale prop snapshots while keeping durable picks/results/CLV intact."""
from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta, timezone

from prop_hunter_shared_utils import log, supabase_client

TABLE = "prop_hunter_prop_snapshots"
DAYS = max(3, int(os.getenv("PH_SNAPSHOT_RETENTION_DAYS", "7")))


def cutoff_iso(days: int = DAYS) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def apply_retention(days: int = DAYS, batch_size: int = 250, max_batches: int = 100) -> int:
    sb = supabase_client()
    if sb is None:
        raise RuntimeError("Supabase missing")
    cutoff = cutoff_iso(max(3, int(days)))
    batch_size = max(1, min(1000, int(batch_size)))
    total = 0
    for _ in range(max(1, int(max_batches))):
        # Bound each transaction. The former all-at-once DELETE timed out.
        rows = sb.table(TABLE).select("snapshot_id").lt("created_at", cutoff).limit(batch_size).execute().data or []
        ids = [row["snapshot_id"] for row in rows]
        if not ids:
            log(f"snapshot retention complete requested={total} cutoff={cutoff}")
            return total
        sb.table(TABLE).delete().in_("snapshot_id", ids).lt("created_at", cutoff).execute()
        total += len(ids)
    log(f"snapshot retention batch budget reached requested={total}; remaining stale rows deferred to next run")
    return total


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--days", type=int, default=DAYS)
    args = parser.parse_args()
    days = max(3, int(args.days))
    cutoff = cutoff_iso(days)
    if args.apply:
        apply_retention(days)
    else:
        log(f"snapshot retention dry-run days={days} cutoff={cutoff}")


if __name__ == "__main__":
    main()
