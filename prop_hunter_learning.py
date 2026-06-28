#!/usr/bin/env python3
"""
PROP HUNTER V10 — SIMPLE LEARNING WEIGHTS
"""

import os

try:
    from supabase import create_client
except Exception:
    create_client = None

def _sb():
    if create_client is None:
        return None
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    if not url or not key:
        return None
    try:
        return create_client(url, key)
    except Exception:
        return None

def get_rule_weight(rule_id):
    c = _sb()
    if c is None or not rule_id:
        return 1.0
    try:
        res = c.table("prop_hunter_rule_performance").select("learned_weight,sample_size").eq("rule_id", rule_id).limit(1).execute()
        rows = res.data or []
        if not rows:
            return 1.0
        if int(rows[0].get("sample_size") or 0) < 25:
            return 1.0
        return float(rows[0].get("learned_weight") or 1.0)
    except Exception:
        return 1.0

def apply_learning_to_pick(p, rule_id):
    w = get_rule_weight(rule_id)
    try:
        prob = float(getattr(p, "probability", 0) or 0)
        edge = float(getattr(p, "edge_pct", 0) or 0)
        setattr(p, "probability", round(max(0.01, min(0.98, prob * (0.90 + 0.10 * w))), 4))
        setattr(p, "edge_pct", round(edge * (0.85 + 0.15 * w), 2))
        f = getattr(p, "features", None)
        if f is None:
            setattr(p, "features", {})
            f = getattr(p, "features")
        if isinstance(f, dict):
            f["learned_weight"] = w
            f["rule_id"] = rule_id
    except Exception:
        pass
    return p
