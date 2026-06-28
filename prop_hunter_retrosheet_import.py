#!/usr/bin/env python3
"""
PROP HUNTER — RETROSHEET IMPORT PREP
====================================

Retrosheet is historical MLB event data. This safe importer expects local CSV/JSON
files in RETROSHEET_DIR and stores raw snapshots.
"""

from __future__ import annotations

import os
import csv
from pathlib import Path

from prop_hunter_shared_utils import upsert_rows, safe_json_write, log, hash_key, now_iso

OUT = "prop_hunter_retrosheet_import_raw.json"

def main():
    d = Path(os.getenv("RETROSHEET_DIR", "retrosheet_data"))
    if not d.exists():
        log("Retrosheet skipped: retrosheet_data folder not found")
        safe_json_write(OUT, [])
        return
    rows = []
    for p in list(d.glob("*.csv"))[:int(os.getenv("RETROSHEET_FILE_CAP", "20"))]:
        with p.open("r", encoding="utf-8", errors="ignore", newline="") as f:
            reader = csv.DictReader(f)
            for i, r in enumerate(reader):
                rows.append({
                    "source_key": "retrosheet",
                    "section": "mlb_historical_events",
                    "entity_key": hash_key(p.name, i, r),
                    "payload": dict(r),
                    "updated_at": now_iso(),
                })
                if len(rows) >= int(os.getenv("RETROSHEET_ROW_CAP", "10000")):
                    break
    safe_json_write(OUT, rows)
    upsert_rows("prop_hunter_source_snapshots", rows, "source_key,section,entity_key")
    log(f"retrosheet import done: {len(rows)} rows")

if __name__ == "__main__":
    main()
