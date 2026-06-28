#!/usr/bin/env python3
"""
PROP HUNTER — MLB STATCAST BACKFILL
===================================

Source:
- pybaseball statcast_batter / statcast_pitcher if installed

Writes:
- prop_hunter_source_snapshots
- prop_hunter_statcast_backfill.json
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

from prop_hunter_shared_utils import safe_json_write, upsert_rows, log, warn, norm_name, hash_key, now_iso

OUT = "prop_hunter_statcast_backfill.json"

def run_statcast(start_dt=None, end_dt=None):
    try:
        from pybaseball import statcast
    except Exception as e:
        warn(f"pybaseball unavailable: {e}")
        return []
    end_dt = end_dt or datetime.utcnow().date().isoformat()
    start_dt = start_dt or (datetime.utcnow().date() - timedelta(days=int(os.getenv("STATCAST_DAYS", "7")))).isoformat()
    try:
        df = statcast(start_dt=start_dt, end_dt=end_dt)
    except Exception as e:
        warn(f"statcast failed: {e}")
        return []
    rows = []
    cap = int(os.getenv("STATCAST_ROW_CAP", "20000"))
    for _, r in df.head(cap).iterrows():
        rows.append({
            "source_key": "pybaseball_statcast",
            "section": "mlb_statcast_pitch",
            "entity_key": hash_key(r.get("game_pk"), r.get("at_bat_number"), r.get("pitch_number")),
            "payload": dict(r),
            "updated_at": now_iso(),
        })
    return rows

def main():
    rows = run_statcast(os.getenv("STATCAST_START"), os.getenv("STATCAST_END"))
    safe_json_write(OUT, rows)
    upsert_rows("prop_hunter_source_snapshots", rows, "source_key,section,entity_key")
    log(f"statcast backfill done: {len(rows)} rows")

if __name__ == "__main__":
    main()
