#!/usr/bin/env python3
"""PROP HUNTER — source manager / trust layer.

Reads learned source health from Supabase or the committed JSON fallback and
provides cheap weights to the card engine. No external HTTP calls are made.
"""
from __future__ import annotations
import json, math
from pathlib import Path
from typing import Any, Dict
from prop_hunter_shared_utils import select_rows, safe_json_write, log

FILE = Path("prop_hunter_source_trust.json")
_CACHE: Dict[str, Dict[str, Any]] | None = None


def _norm(v: Any) -> str:
    return str(v or "").strip().lower()


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def load_source_trust(refresh: bool = False) -> Dict[str, Dict[str, Any]]:
    global _CACHE
    if _CACHE is not None and not refresh:
        return _CACHE
    rows = select_rows("prop_hunter_source_trust", limit=1000)
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        key = _norm(row.get("source_name"))
        if key:
            out[key] = row
    if not out and FILE.exists():
        try:
            raw = json.loads(FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict): out = raw
        except Exception:
            pass
    _CACHE = out
    return out


def source_weight(source: Any, sport: Any = None, market: Any = None) -> float:
    """Conservative 0.72..1.18 multiplier learned from health/ROI.

    Missing/new sources stay neutral so discovery is not starved.
    """
    key = _norm(source)
    if not key:
        return 1.0
    row = load_source_trust().get(key)
    if not row:
        return 1.0
    try:
        trust = float(row.get("trust_score") if row.get("trust_score") is not None else 50.0)
    except Exception:
        trust = 50.0
    # trust_score is stored 0..100
    return round(_clamp(0.72 + (trust / 100.0) * 0.46, 0.72, 1.18), 3)


def source_is_blocked(source: Any) -> bool:
    key = _norm(source)
    if not key:
        return False
    row = load_source_trust().get(key)
    if not row:
        return False
    raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
    try:
        trust = float(row.get("trust_score") or 50)
    except Exception:
        trust = 50
    samples = int(raw.get("settled_samples") or 0)
    # Only block with meaningful evidence. New sources remain in shadow/neutral.
    return samples >= 40 and trust < 28


def export_local() -> Dict[str, Dict[str, Any]]:
    data = load_source_trust(refresh=True)
    safe_json_write(FILE, data)
    log(f"source manager: {len(data)} learned sources")
    return data


if __name__ == "__main__":
    export_local()
