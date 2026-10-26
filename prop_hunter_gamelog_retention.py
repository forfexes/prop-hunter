#!/usr/bin/env python3
"""Keep only the newest N player games per sport/league/player.

This preserves L5/L10/L15 feature history while preventing the gamelog
table from growing without bound. Picks, results, CLV and prop snapshots are
not touched.
"""
from __future__ import annotations

import argparse
import os
from collections import defaultdict
from typing import Dict, List, Tuple

from prop_hunter_shared_utils import log, supabase_client

TABLE = "prop_hunter_player_gamelogs"
KEEP = max(15, int(os.getenv("PH_GAMELOG_KEEP_PER_PLAYER", "15")))
PAGE = 1000
DELETE_BATCH = max(100, min(1000, int(os.getenv("PH_GAMELOG_DELETE_BATCH", "500"))))


def fetch_meta() -> List[Dict]:
    sb = supabase_client()
    if sb is None:
        raise RuntimeError("Supabase missing")
    rows: List[Dict] = []
    start = 0
    while True:
        end = start + PAGE - 1
        res = (
            sb.table(TABLE)
            .select("id,sport,league,normalized_name,game_date,created_at")
            .order("id", desc=False)
            .range(start, end)
            .execute()
        )
        batch = res.data or []
        rows.extend(batch)
        if len(batch) < PAGE:
            break
        start = end + 1
    return rows


def rank_delete_ids(rows: List[Dict]) -> List[int]:
    groups: Dict[Tuple[str, str, str], List[Dict]] = defaultdict(list)
    for row in rows:
        name = str(row.get("normalized_name") or "").strip()
        if not name:
            continue
        key = (
            str(row.get("sport") or "").upper(),
            str(row.get("league") or "").upper(),
            name,
        )
        groups[key].append(row)

    delete_ids: List[int] = []
    for items in groups.values():
        items.sort(
            key=lambda r: (
                str(r.get("game_date") or ""),
                str(r.get("created_at") or ""),
                int(r.get("id") or 0),
            ),
            reverse=True,
        )
        delete_ids.extend(int(r["id"]) for r in items[KEEP:] if r.get("id") is not None)
    return delete_ids


def apply_delete(ids: List[int]) -> None:
    if not ids:
        return
    sb = supabase_client()
    if sb is None:
        raise RuntimeError("Supabase missing")
    total = len(ids)
    for start in range(0, total, DELETE_BATCH):
        batch = ids[start:start + DELETE_BATCH]
        sb.table(TABLE).delete().in_("id", batch).execute()
        log(f"gamelog retention deleted {min(start + len(batch), total)}/{total}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="delete rows instead of dry-run")
    args = parser.parse_args()

    rows = fetch_meta()
    ids = rank_delete_ids(rows)
    log(f"gamelog retention keep_per_player={KEEP} scanned={len(rows)} delete={len(ids)}")
    if args.apply:
        apply_delete(ids)
        log(f"gamelog retention applied deleted={len(ids)}")
    else:
        log("gamelog retention dry-run; pass --apply to delete")


if __name__ == "__main__":
    main()
