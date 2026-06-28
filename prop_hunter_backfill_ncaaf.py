#!/usr/bin/env python3
"""
PROP HUNTER — NCAAF BACKFILL CFBD PREP
======================================

Env:
CFBD_API_KEY optional

This is a safe CFBD connector scaffold for College Football data.
"""

from __future__ import annotations

import os
from prop_hunter_shared_utils import http_json, upsert_rows, safe_json_write, log, warn, hash_key, now_iso

OUT = "prop_hunter_backfill_ncaaf_raw.json"
BASE = "https://api.collegefootballdata.com"

def headers():
    k = os.getenv("CFBD_API_KEY", "").strip()
    return {"Authorization": f"Bearer {k}"} if k else {}

def main():
    if not os.getenv("CFBD_API_KEY", "").strip():
        warn("CFBD_API_KEY missing; NCAAF skipped")
        safe_json_write(OUT, [])
        return
    year = os.getenv("NCAAF_SEASON", "2025")
    data = http_json(f"{BASE}/stats/player/season", params={"year": year}, headers=headers(), retries=1) or []
    rows = []
    for it in data if isinstance(data, list) else []:
        rows.append({
            "source_key": "cfbd",
            "section": "ncaaf_player_season",
            "entity_key": hash_key(year, it.get("player"), it.get("team"), it.get("category")),
            "payload": it,
            "updated_at": now_iso(),
        })
    safe_json_write(OUT, rows)
    upsert_rows("prop_hunter_source_snapshots", rows, "source_key,section,entity_key")
    log(f"NCAAF backfill done: {len(rows)} rows")

if __name__ == "__main__":
    main()
