"""Owner-original-aware rescue scheduling.

When only NBA has approved, genuinely cleaned owner masters, source rescue
must not spend 17 of 18 preview slots on NFL candidates that the Telegram
owner-only release will always reject. This is NOT a model-score shortcut:
the exact final Single quality gate (odds/probability/edge) is reused here.
Other sports are still gathered and scored for offline diagnostics.
"""
from __future__ import annotations

import os
from collections import Counter


def owner_only_mode() -> bool:
    return (
        os.getenv("PH_OWNER_APPROVED_ALL_SPORTS", "0").strip() == "1"
        and os.getenv("PH_NBA_OWNER_ORIGINALS", "0").strip() == "1"
        and os.getenv("PH_ENFORCE_OWNER_QUALITY", "0").strip() == "1"
    )


def select_publishable_owner_rescue(candidates):
    """Return (preserved_order_pool, stats) before any 18-pick diversity cap.

    Cannot create, mutate, reprioritize by guessed EV or fabricate a sports
    template. Actual Telegram rendering still checks photos, kickoff,
    bookmaker source, ticket identity and immutable source artwork.
    """
    pool = list(candidates)
    if not owner_only_mode():
        return pool, {"mode": "all_sports", "retained": len(pool)}
    from prop_hunter_image_publication_gate import owner_single_quality

    accepted = []
    blocked = Counter()
    for candidate in pool:
        sport = str(
            getattr(candidate, "source_sport", None)
            or getattr(candidate, "sport", "") or ""
        ).strip().upper()
        if sport not in ("NBA", "BASKETBALL_NBA"):
            blocked["unapproved_league"] += 1
            continue
        eligible, why = owner_single_quality(candidate)
        if not eligible:
            blocked[why] += 1
            continue
        accepted.append(candidate)
    return accepted, {
        "mode": "nba_originals_only",
        "considered": len(pool),
        "retained": len(accepted),
        "blocked": dict(blocked),
    }
