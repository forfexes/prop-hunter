#!/usr/bin/env python3
"""Bounded EuroLeague player-game backfill from ESPN boxscores.

Initial mode scans enough completed games to fill roughly the newest 40 games
per player. Later runs only scan recent days. Global retention remains the final
40-game storage guard.
"""
from __future__ import annotations

import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from prop_hunter_results_euroleague import parse_summary, scoreboard, summary
from prop_hunter_shared_utils import log, select_rows, upsert_rows

LEAGUE = "EUROLEAGUE"
KEEP = max(30, min(40, int(os.getenv("PH_EUROLEAGUE_LAST_N", "40"))))
FULL_LOOKBACK_DAYS = max(300, min(500, int(os.getenv("PH_EUROLEAGUE_BACKFILL_DAYS", "400"))))
INCREMENTAL_DAYS = max(3, min(14, int(os.getenv("PH_EUROLEAGUE_INCREMENTAL_DAYS", "7"))))
FULL_EVENT_CAP = max(250, min(600, int(os.getenv("PH_EUROLEAGUE_MAX_EVENTS", "450"))))
INCREMENTAL_EVENT_CAP = max(10, min(80, int(os.getenv("PH_EUROLEAGUE_INCREMENTAL_MAX_EVENTS", "40"))))
INITIAL_COMPLETE_ROWS = max(3000, int(os.getenv("PH_EUROLEAGUE_INITIAL_COMPLETE_ROWS", "5000")))
BATCH = max(100, min(1000, int(os.getenv("PH_EUROLEAGUE_BATCH", "500"))))


def existing_rows() -> List[Dict[str, Any]]:
    return select_rows(
        "prop_hunter_player_gamelogs",
        limit=None,
        filters={"league": LEAGUE},
        order_by="id",
    )


def _event_date(event: Dict[str, Any]) -> str:
    return str(event.get("date") or "")[:10]


def fetch_events(days: int) -> List[Dict[str, Any]]:
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days)
    # ESPN accepts date ranges. Split into 31-day chunks so one oversized
    # response cannot silently truncate a season.
    events: Dict[str, Dict[str, Any]] = {}
    cursor = start
    while cursor <= end:
        chunk_end = min(end, cursor + timedelta(days=30))
        date_arg = f"{cursor.strftime('%Y%m%d')}-{chunk_end.strftime('%Y%m%d')}"
        for event in scoreboard(date_arg):
            eid = str(event.get("id") or "")
            status = ((event.get("status") or {}).get("type") or {})
            if eid and status.get("completed"):
                events[eid] = event
        cursor = chunk_end + timedelta(days=1)
    rows = list(events.values())
    rows.sort(key=lambda e: (_event_date(e), str(e.get("id") or "")), reverse=True)
    return rows


def main() -> None:
    existing = existing_rows()
    full_mode = len(existing) < INITIAL_COMPLETE_ROWS
    days = FULL_LOOKBACK_DAYS if full_mode else INCREMENTAL_DAYS
    event_cap = FULL_EVENT_CAP if full_mode else INCREMENTAL_EVENT_CAP

    counts: Counter = Counter()
    if full_mode:
        # Existing partial rows still count toward the per-player cap.
        for row in existing:
            name = str(row.get("normalized_name") or "").strip()
            if name:
                counts[name] += 1

    events = fetch_events(days)[:event_cap]
    log(
        f"EuroLeague backfill mode={'full' if full_mode else 'incremental'} "
        f"existing={len(existing)} days={days} events={len(events)} cap={event_cap}"
    )

    out: List[Dict[str, Any]] = []
    processed = 0
    for event in events:
        eid = str(event.get("id") or "")
        if not eid:
            continue
        try:
            rows = parse_summary(summary(eid))
        except Exception as exc:
            log(f"EuroLeague summary failed event={eid}: {type(exc).__name__}: {exc}")
            continue
        processed += 1
        for row in rows:
            nk = str(row.get("normalized_name") or "").strip()
            if not nk:
                continue
            if full_mode and counts.get(nk, 0) >= KEEP:
                continue
            out.append(row)
            if full_mode:
                counts[nk] += 1
        if len(out) >= BATCH:
            upsert_rows(
                "prop_hunter_player_gamelogs",
                out,
                "sport,league,season,game_id,normalized_name",
            )
            out.clear()
        if processed % 50 == 0:
            log(f"EuroLeague backfill progress events={processed}/{len(events)}")

    if out:
        upsert_rows(
            "prop_hunter_player_gamelogs",
            out,
            "sport,league,season,game_id,normalized_name",
        )
    log(f"EuroLeague backfill done processed_events={processed}")


if __name__ == "__main__":
    main()
