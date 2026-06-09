"""Smart per-sport season detection."""
from __future__ import annotations

from datetime import datetime, timezone

SUPPORTED_SPORTS = {
    "baseball_mlb",
    "basketball_nba",
    "basketball_wnba",
    "basketball_euroleague",
    "americanfootball_nfl",
}


def season_for(sport: str, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    y, m = now.year, now.month
    if sport == "baseball_mlb":
        return y if 3 <= m <= 11 else y - 1
    if sport in ("basketball_nba", "basketball_euroleague"):
        return y - 1 if m < 10 else y
    if sport == "basketball_wnba":
        return y if 5 <= m <= 10 else y - 1
    if sport == "americanfootball_nfl":
        return y - 1 if m < 9 else y
    return y


def is_nfl_offseason(now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    return now.month in (3, 4, 5, 6, 7, 8)
