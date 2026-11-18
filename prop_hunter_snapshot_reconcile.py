#!/usr/bin/env python3
"""Reconcile snapshot IDs after a non-destructive migration, including retention races."""
from __future__ import annotations
import json
import sys
from datetime import datetime,timezone
from prop_hunter_snapshot_migrate import credentials, pages, api

def ids(endpoint,key):
    result=set()
    for batch in pages(endpoint,key,"snapshot_id"):
        for row in batch:
            sid=row["snapshot_id"]
            if sid in result:
                raise RuntimeError("Duplicate snapshot ID in read")
            result.add(sid)
    return result

def main():
    primary,pk=credentials("primary")
    secondary,sk=credentials("secondary")
    if primary==secondary:
        raise RuntimeError("Source and target are identical")
    originals=ids(primary,pk)
    if not originals:
        raise RuntimeError("Source unexpectedly empty")
    current=ids(secondary,sk)
    missing=originals-current
    print(f"RECONCILE: primary={len(originals)} secondary={len(current)} missing={len(missing)}",flush=True)
    if missing:
        transferred=0
        for batch in pages(primary,pk,"*"):
            selected=[r for r in batch if r["snapshot_id"] in missing]
            if selected:
                api("POST",secondary,sk,params={"on_conflict":"snapshot_id"},data=selected)
                transferred+=len(selected)
        if transferred!=len(missing):
            raise RuntimeError("Source rows missing during reconciliation")
    verified=ids(secondary,sk)
    still_missing=originals-verified
    if still_missing:
        raise RuntimeError(f"RECONCILE FAILED: {len(still_missing)} original IDs still missing")
    if ids(primary,pk)!=originals:
        raise RuntimeError("Primary changed during reconciliation")
    result={
        "status":"verified",
        "primary_count":len(originals),
        "secondary_count":len(verified),
        "missing_after_repair":0,
        "repaired_count":len(missing),
        "primary_deleted":False,
        "verified_at":datetime.now(timezone.utc).isoformat(),
    }
    with open("prop_hunter_snapshot_reconcile_report.json","w",encoding="utf-8") as f:
        json.dump(result,f,indent=2)
    print("RECONCILE VERIFIED: "+json.dumps(result),flush=True)

if __name__=="__main__":
    try: main()
    except Exception as exc:
        print("RECONCILE FAILED: "+str(exc),file=sys.stderr)
        sys.exit(1)
