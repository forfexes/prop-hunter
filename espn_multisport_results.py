#!/usr/bin/env python3
"""
PROP HUNTER — ESPN MULTISPORT RESULTS BACKUP
============================================

Backup scoreboard/summary downloader for NBA/WNBA/NFL/MLB.
Saves raw snapshots for later parsing.
"""

from __future__ import annotations

import os
from datetime import datetime

from prop_hunter_shared_utils import http_json, upsert_rows, safe_json_write, log, hash_key, now_iso

OUT = "espn_multisport_results_raw.json"

SPORT_ENDPOINTS = {
    "NBA": ("basketball", "nba"),
    "WNBA": ("basketball", "wnba"),
    "NFL": ("football", "nfl"),
    "MLB": ("baseball", "mlb"),
}

def fetch_scoreboard(sport_key):
    sport, league = SPORT_ENDPOINTS[sport_key]
    url = f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard"
    return http_json(url, retries=1) or {}

def main():
    rows = []
    for key in os.getenv("ESPN_RESULT_SPORTS", "NBA,WNBA,NFL,MLB").split(","):
        key = key.strip().upper()
        if key not in SPORT_ENDPOINTS:
            continue
        data = fetch_scoreboard(key)
        for ev in data.get("events", []) or []:
            rows.append({
                "source_key": "espn_scoreboard",
                "section": key.lower() + "_scoreboard",
                "entity_key": str(ev.get("id") or hash_key(ev)),
                "payload": ev,
                "updated_at": now_iso(),
            })
    safe_json_write(OUT, rows)
    upsert_rows("prop_hunter_source_snapshots", rows, "source_key,section,entity_key")
    log(f"espn multisport done: {len(rows)} snapshots")

if __name__ == "__main__":
    main()
