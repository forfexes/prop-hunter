"""Apply league approval before allocating a limited source-rescue pool."""
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
    from prop_hunter_image_cards import league_of
    from prop_hunter_image_publication_gate import (
        owner_single_quality, pre_match_quote_provenance, sport_card_enabled,
    )

    accepted = []
    blocked = Counter()
    for candidate in pool:
        sport = getattr(candidate, "source_sport", None) or getattr(candidate, "sport", None)
        league = league_of(sport)
        if league and league[1] == "nba":
            eligible, why = owner_single_quality(candidate)
        elif sport_card_enabled(league):
            eligible, why = pre_match_quote_provenance(candidate)
        else:
            blocked["unapproved_league"] += 1
            continue
        if not eligible:
            blocked[why] += 1
            continue
        accepted.append(candidate)
    return accepted, {
        "mode": "approved_leagues",
        "considered": len(pool),
        "retained": len(accepted),
        "blocked": dict(blocked),
    }
