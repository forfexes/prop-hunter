#!/usr/bin/env python3
"""Compatibility wrapper around the autonomous free-source orchestrator.

When the workflow collected sources a few minutes earlier, the bot reuses that fresh
snapshot instead of hitting every website twice.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from prop_hunter_shared_utils import safe_json_load
from prop_hunter_source_orchestrator import collect as _collect

log = logging.getLogger("prop_hunter_source_hub")
CACHE = Path("prop_hunter_all_sources.json")


def _fresh_cache(max_minutes: int = 20) -> List[Dict]:
    if not CACHE.exists(): return []
    age = (datetime.now(timezone.utc).timestamp() - CACHE.stat().st_mtime) / 60
    if age > max_minutes: return []
    rows = safe_json_load(CACHE, []) or []
    return rows if isinstance(rows, list) else []


def collect(sport_filter: Optional[str] = None) -> List[Dict]:
    rows = _fresh_cache()
    if rows:
        if sport_filter:
            needle = sport_filter.upper()
            aliases = {"MLB":"MLB","NBA":"NBA","WNBA":"WNBA","NFL":"NFL","NHL":"NHL"}
            target = aliases.get(needle, needle)
            rows = [r for r in rows if str(r.get("sport") or r.get("league") or "").upper() == target]
        log.info("source hub fresh workflow cache: %d rows", len(rows))
        return rows
    return _collect(sport_filter=sport_filter, mode="fast")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    data = collect()
    print(f"PROP HUNTER source hub rows={len(data)}")
