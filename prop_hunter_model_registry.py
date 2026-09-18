#!/usr/bin/env python3
"""PROP HUNTER — model registry metadata.

The registry controls when a market is mature enough to influence stakes/models.
It does not train during card runs.
"""
from __future__ import annotations
from pathlib import Path
import json
from prop_hunter_shared_utils import select_rows, safe_json_write, now_iso, log

FILE=Path("prop_hunter_model_registry.json")
MIN_SHADOW=20
MIN_ACTIVE=60


def build_registry():
    rows=select_rows("prop_hunter_rule_performance", limit=5000)
    reg={"updated_at":now_iso(),"groups":{}}
    for r in rows:
        if r.get("group_type") not in {"market","sport_market"}: continue
        n=int(r.get("bets") or r.get("sample_size") or 0)
        roi=float(r.get("roi") or 0)
        w=float(r.get("learning_weight") or 1.0)
        if n < MIN_SHADOW: status="collecting"
        elif n < MIN_ACTIVE: status="shadow"
        elif w <= 0.78 and roi < -0.08: status="degraded"
        else: status="active"
        reg["groups"][str(r.get("group_key"))]={
            "group_type":r.get("group_type"),"samples":n,"roi":roi,"hit_rate":r.get("hit_rate"),
            "weight":w,"status":status,"min_active_samples":MIN_ACTIVE,
        }
    safe_json_write(FILE,reg)
    log(f"model registry: {len(reg['groups'])} groups")
    return reg


def load_registry():
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"groups":{}}

if __name__ == "__main__": build_registry()
