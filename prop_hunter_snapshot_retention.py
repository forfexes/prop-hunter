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


def apply_retention(days: int = DAYS) -> None:
    sb = supabase_client()
    if sb is None:
        raise RuntimeError("Supabase missing")
    cutoff = cutoff_iso(days)
    sb.table(TABLE).delete().lt("created_at", cutoff).execute()
    log(f"snapshot retention applied days={days} cutoff={cutoff}")


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
