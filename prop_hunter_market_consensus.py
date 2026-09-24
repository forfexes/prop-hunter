#!/usr/bin/env python3
"""Lightweight cross-source market consensus for PROP HUNTER snapshots.

The module intentionally stores enrichment inside ``raw.consensus`` so it works with
all existing Supabase schemas without requiring a migration. It never changes the
observed line/price used for a pick.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Tuple


def _f(value: Any):
    try:
        return float(value)
    except Exception:
        return None


def _key(row: Dict[str, Any]) -> Tuple[str, str, str, str, str, str]:
    return (
        str(row.get("sport") or row.get("league") or "").upper(),
        str(row.get("source_event_id") or row.get("event_id") or row.get("game_id") or ""),
        str(row.get("player_name") or "").strip().lower(),
        str(row.get("market_key") or row.get("market") or "").strip().lower(),
        str(row.get("direction") or "").strip().lower(),
        str(row.get("line") if row.get("line") is not None else ""),
    )


def enrich(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = [dict(r) for r in (rows or []) if isinstance(r, dict)]
    groups = defaultdict(list)
    for row in out:
        dec = _f(row.get("odds_decimal") or row.get("odds"))
        if dec and dec > 1:
            groups[_key(row)].append((row, dec))

    summaries = {}
    for key, items in groups.items():
        prices = [p for _, p in items]
        books = sorted({str(r.get("bookmaker") or r.get("source") or "").lower() for r, _ in items if r.get("bookmaker") or r.get("source")})
        sources = sorted({str(r.get("source") or "").lower() for r, _ in items if r.get("source")})
        summaries[key] = {
            "quote_count": len(prices),
            "book_count": len(books),
            "source_count": len(sources),
            "books": books,
            "sources": sources,
            "best_decimal": round(max(prices), 4),
            "median_decimal": round(float(statistics.median(prices)), 4),
        }

    for row in out:
        summary = summaries.get(_key(row))
        if not summary:
            continue
        raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
        raw = dict(raw)
        raw["consensus"] = summary
        row["raw"] = raw
    return out
