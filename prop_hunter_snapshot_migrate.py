#!/usr/bin/env python3
"""One-time, non-destructive migration of original PROP HUNTER snapshot rows.

Reads the legacy primary, upserts to the dedicated secondary, and independently
verifies every snapshot_id. NEVER deletes primary rows; freeing primary storage
is a separate, gated database operation after verification.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone

import requests

TABLE = "prop_hunter_prop_snapshots"
PAGE = 500
RETRYABLE = {408, 429, 500, 502, 503, 504}


def credentials(prefix: str):
    if prefix == "primary":
        url = os.getenv("SUPABASE_URL", "").rstrip("/")
        key = os.getenv("SUPABASE_KEY", "")
    else:
        url = os.getenv("SUPABASE_SECONDARY_URL", "").rstrip("/")
        key = os.getenv("SUPABASE_SECONDARY_SERVICE_ROLE_KEY", "")
    if not url.startswith("https://") or not key:
        raise RuntimeError(f"{prefix} Supabase credentials missing")
    return url + "/rest/v1/" + TABLE, key


def api(method, endpoint, key, *, params=None, data=None):
    headers = {
        "apikey": key,
        "Authorization": "Bearer " + key,
        "Accept": "application/json",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
        headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
    for attempt in range(5):
        try:
            res = requests.request(
                method, endpoint, params=params, headers=headers,
                json=data, timeout=(12, 70),
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            if attempt == 4:
                raise RuntimeError(f"{method} network failure after retries") from exc
            time.sleep(min(2 ** attempt, 12))
            continue
        if res.status_code in RETRYABLE and attempt < 4:
            time.sleep(min(2 ** attempt, 12))
            continue
        if not res.ok:
            # Never log headers or credentials.
            raise RuntimeError(f"{method} snapshot API HTTP {res.status_code}: {res.text[:220]}")
        return res
    raise RuntimeError("Snapshot API retries exhausted")


def pages(endpoint, key, fields):
    last = None
    while True:
        params = {"select": fields, "order": "snapshot_id.asc", "limit": str(PAGE)}
        if last is not None:
            params["snapshot_id"] = "gt." + last
        rows = api("GET", endpoint, key, params=params).json()
        if not isinstance(rows, list):
            raise RuntimeError("Unexpected snapshot API response")
        if not rows:
            break
        keys = [r.get("snapshot_id") for r in rows]
        if any(not isinstance(k, str) or not k for k in keys):
            raise RuntimeError("Snapshot missing primary key")
        if last is not None and keys[0] <= last:
            raise RuntimeError("Snapshot paging did not advance")
        if keys != sorted(set(keys)):
            raise RuntimeError("Snapshot paging duplicate or unsorted keys")
        yield rows
        last = keys[-1]
        if len(rows) < PAGE:
            break


def migrate():
    source, sk = credentials("primary")
    target, tk = credentials("secondary")
    if source == target:
        raise RuntimeError("Primary and secondary URLs must differ")
    source_ids = set()
    copied = 0
    samples = {}
    started = datetime.now(timezone.utc).isoformat()
    for rows in pages(source, sk, "*"):
        for i, row in enumerate(rows):
            sid = row["snapshot_id"]
            if sid in source_ids:
                raise RuntimeError("Duplicate snapshot key in source")
            source_ids.add(sid)
            if len(samples) < 24 and (copied + i) % 10000 == 0:
                samples[sid] = (row.get("raw"), row.get("player_name"), row.get("odds_decimal"))
        api("POST", target, tk, params={"on_conflict": "snapshot_id"}, data=rows)
        copied += len(rows)
        if copied % 10000 < PAGE:
            print(f"SNAPSHOT COPY: {copied} original rows upserted", flush=True)
    if not copied:
        raise RuntimeError("Primary snapshots unexpectedly empty: refusing migration success")
    target_ids = set()
    for rows in pages(target, tk, "snapshot_id"):
        target_ids.update(r["snapshot_id"] for r in rows)
    missing = source_ids - target_ids
    if missing:
        raise RuntimeError(f"Snapshot verification failed: {len(missing)} original IDs missing on secondary")
    for sid, expected in samples.items():
        got = api("GET", target, tk, params={"select":"raw,player_name,odds_decimal",
                                           "snapshot_id":"eq." + sid, "limit":"1"}).json()
        if len(got) != 1 or (got[0].get("raw"), got[0].get("player_name"), got[0].get("odds_decimal")) != expected:
            raise RuntimeError("Snapshot sample payload mismatch on secondary")
    # Re-read primary key set to detect concurrent legacy writers during migration.
    after = set()
    for rows in pages(source, sk, "snapshot_id"):
        after.update(r["snapshot_id"] for r in rows)
    if after != source_ids:
        raise RuntimeError(f"Primary changed during migration: before={len(source_ids)} after={len(after)}")
    digest = hashlib.sha256("\n".join(sorted(source_ids)).encode()).hexdigest()
    report = {
        "status": "verified",
        "source_count": len(source_ids),
        "target_count": len(target_ids),
        "missing_source_ids": 0,
        "verified_sample_count": len(samples),
        "primary_unchanged": True,
        "sha256_source_ids": digest,
        "started_at": started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "primary_deleted": False,
    }
    with open("prop_hunter_snapshot_migration_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print("SNAPSHOT MIGRATION VERIFIED: " + json.dumps(report, sort_keys=True), flush=True)


if __name__ == "__main__":
    try:
        migrate()
    except Exception as exc:
        print(f"SNAPSHOT MIGRATION FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
