"""Disk-backed cache with dynamic TTL."""
from __future__ import annotations

import json
import os
import time
from typing import Any, Optional

from .config import ODDS_CACHE_FILE, ODDS_CACHE_TTL_MAX_SECONDS
from .logging_setup import get_logger

log = get_logger(__name__)


def dynamic_ttl(earliest_game_iso: Optional[str], now_ts: Optional[float] = None) -> int:
    if not earliest_game_iso:
        return ODDS_CACHE_TTL_MAX_SECONDS
    try:
        from datetime import datetime
        ts = datetime.fromisoformat(earliest_game_iso.replace("Z", "+00:00")).timestamp()
        now = now_ts or time.time()
        delta = max(0, ts - now)
        return int(min(ODDS_CACHE_TTL_MAX_SECONDS, max(60, delta / 3)))
    except Exception:
        return ODDS_CACHE_TTL_MAX_SECONDS


def load_odds_cache(cache_file: str = ODDS_CACHE_FILE) -> dict:
    if not os.path.exists(cache_file):
        return {}
    try:
        with open(cache_file) as f:
            data = json.load(f)
        ts = data.get("timestamp", 0)
        ttl = data.get("ttl", ODDS_CACHE_TTL_MAX_SECONDS)
        age = time.time() - ts
        if age < ttl:
            log.info("Odds cache HIT (age=%.0fmin, ttl=%.0fmin)", age / 60, ttl / 60)
            return data.get("odds", {})
        log.info("Odds cache EXPIRED (age=%.0fmin > ttl=%.0fmin)", age / 60, ttl / 60)
    except (OSError, json.JSONDecodeError) as e:
        log.warning("cache load failed: %s", e)
    return {}


def save_odds_cache(odds_data: dict, earliest_game_iso: Optional[str] = None,
                    cache_file: str = ODDS_CACHE_FILE) -> None:
    ttl = dynamic_ttl(earliest_game_iso)
    try:
        with open(cache_file, "w") as f:
            json.dump({"timestamp": time.time(), "ttl": ttl, "odds": odds_data}, f, indent=2)
        log.info("Odds cache saved (%d events, ttl=%dmin)", len(odds_data), ttl // 60)
    except OSError as e:
        log.warning("cache save failed: %s", e)


class MemCache:
    def __init__(self, ttl_seconds: int = 3600):
        self._store: dict[str, tuple[float, Any]] = {}
        self.ttl = ttl_seconds

    def get(self, key: str) -> Any:
        if key not in self._store:
            return None
        ts, val = self._store[key]
        if time.time() - ts > self.ttl:
            del self._store[key]
            return None
        return val

    def set(self, key: str, val: Any) -> None:
        self._store[key] = (time.time(), val)

    def clear(self) -> None:
        self._store.clear()
