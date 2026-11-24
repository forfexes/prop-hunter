"""Pure, independent NBA fixture-tipoff audit.

Prices are not event start times. An odds feed can contain an 01:11 timestamp
for a game that officially starts at 01:00. Never silently rewrite a bet's
fixture metadata; retain source values but prevent an unverified image/send.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math


def kickoff_comparison(claimed, official, tolerance_seconds=90):
    """Return 'match', 'conflict' or 'unverified' without any network calls."""
    try:
        def aware(value):
            t = (value if isinstance(value, datetime) else
                 datetime.fromisoformat(str(value).replace("Z", "+00:00")))
            if t.tzinfo is None or t.utcoffset() is None:
                return None
            return t.astimezone(timezone.utc)
        a, b = aware(claimed), aware(official)
        if a is None or b is None:
            return "unverified"
        delta = abs((a-b).total_seconds())
        if not math.isfinite(delta):
            return "unverified"
        return "match" if delta <= tolerance_seconds else "conflict"
    except (TypeError, ValueError, OverflowError):
        return "unverified"


def mark_official_conflict(prop, official_start):
    """Mark only positively verified discrepancies; never change source odds."""
    features = dict(getattr(prop, "features", {}) or {})
    declared = getattr(prop, "commence_time", None) or features.get("commence_time")
    outcome = kickoff_comparison(declared, official_start)
    if outcome == "conflict":
        features["verified_fixture_kickoff_conflict"] = True
        features["verified_fixture_kickoff_source"] = "ESPN_NBA_TWO_TEAM_SCHEDULE"
        features["verified_fixture_kickoff_expected"] = str(official_start)
        prop.features = features
    return outcome
