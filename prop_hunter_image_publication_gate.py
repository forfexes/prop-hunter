"""Preflight all NBA owner-original Telegram cards without dropping other picks.

Only source-verified original PNG cards may be published. Unknown images remain
unpublished (not silently replaced by text), and the history writer receives
only the actual eligible subset. No network calls except through supplied
image-card renderer; no Telegram or Supabase access.
"""
from __future__ import annotations


_PNG_MAGIC=bytes((137,80,78,71,13,10,26,10))


def filter_verified_nba_images(picks, cards):
    """Return (publishable_picks, blocked_count).

    Exact NBA recognition mirrors the production renderer. Missing/non-PNG
    originals are individually deferred, not turned into Telegram texts.
    Any unapproved non-NBA sport stays on its own existing route.
    """
    accepted=[]
    blocked=0
    for pick in picks:
        details=list(getattr(pick,"leg_details",None) or [])
        hint=(getattr(pick,"source_sport",None)
              or getattr(pick,"sport",None)
              or (details[0].get("sport") if details else None))
        league=cards.league_of(hint)
        if not league or league[1]!="nba":
            accepted.append(pick)
            continue
        result=cards.build_for_pick(pick)
        if isinstance(result,(bytes,bytearray)) and bytes(result).startswith(_PNG_MAGIC):
            # Production will reuse the exact verified artwork bytes from
            # preflight. Never fetch photos or redraw a second time after the
            # decision, which could change the card or hit a transient API.
            setattr(pick,"_verified_owner_png",bytes(result))
            accepted.append(pick)
        else:
            blocked+=1
    return accepted,blocked
