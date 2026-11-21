"""Preflight all NBA owner-original Telegram cards without dropping other picks.

Only source-verified original PNG cards may be published. Unknown images remain
unpublished (not silently replaced by text), and the history writer receives
only the actual eligible subset. No network calls except through supplied
image-card renderer; no Telegram or Supabase access.
"""
from __future__ import annotations

from io import BytesIO
import os
from PIL import Image


_PNG_MAGIC=bytes((137,80,78,71,13,10,26,10))


def _valid_owner_png(value):
    """Reject truncated images or mislabeled thumbnails before Telegram upload."""
    if not isinstance(value,(bytes,bytearray)) or not value.startswith(_PNG_MAGIC):
        return False
    try:
        with Image.open(BytesIO(value)) as source:
            if source.format!="PNG" or source.width<900 or source.height<1000:
                return False
            source.verify()
        return True
    except (ValueError,OSError,SyntaxError):
        return False


def filter_verified_nba_images(picks, cards):
    """Return (publishable_picks, blocked_count).

    Exact NBA recognition mirrors the production renderer. Missing/non-PNG
    originals are individually deferred, not turned into Telegram texts.
    Any unapproved non-NBA sport stays on its own existing route.
    """
    accepted=[]
    blocked=0
    strict_all=os.getenv("PH_OWNER_APPROVED_ALL_SPORTS","0").strip()=="1"
    for pick in picks:
        details=list(getattr(pick,"leg_details",None) or [])
        # Historical builder/lottery legs may be dictionaries or model
        # objects. A non-dict first leg must not abort the entire send batch.
        first_leg=details[0] if details else None
        first_sport=(first_leg.get("sport") if isinstance(first_leg,dict)
                     else getattr(first_leg,"sport",None))
        hint=(getattr(pick,"source_sport",None)
              or getattr(pick,"sport",None)
              or first_sport)
        league=cards.league_of(hint)
        # Never retain an old validated image after price, player, league or
        # approval state changed. This applies even to legacy non-NBA routes.
        if hasattr(pick,"_verified_owner_png"):
            try:
                delattr(pick,"_verified_owner_png")
            except (AttributeError,TypeError):
                blocked+=1
                continue
        if strict_all:
            # Only NBA has actual approved, sample-free owner PNG masters.
            # NFL/NHL/WNBA/MLB and unknown-source cards must be deferred
            # until THEIR original premium master is formally approved.
            leg_leagues=[cards.league_of(
                leg.get("sport") if isinstance(leg,dict)
                else getattr(leg,"sport",None)) for leg in details]
            if (not league or league[1]!="nba"
                    or any(not item or item[1]!="nba" for item in leg_leagues)):
                blocked+=1
                continue
        # Apply the same all-sport combined-ticket provenance gate to
        # every pick, even one accidentally mislabeled Single/Longshot/Ladder.
        # No cached PNG may bypass the verified bookmaker-price requirement.
        from prop_hunter_combo_prices import publishable_extra
        if not publishable_extra(pick):
            blocked+=1
            continue
        if not league or league[1]!="nba":
            accepted.append(pick)
            continue
        # A pick may be rechecked after bookmaker odds, lineups, photos or
        # ticket provenance changed. Invalidate an old successful preflight
        # before every new check. Otherwise a previously cached image could
        # be uploaded even after the updated pick is rejected.
        # Publishing a combined NBA ticket requires an actual observed
        # bookmaker price AND its ticket identifier. Multiplying authentic
        # single-leg odds is useful for offline analysis, but is not a
        # bookable parlay price and must never reach Telegram as a pick.
        result=cards.build_for_pick(pick)
        if _valid_owner_png(result):
            # Production will reuse the exact verified artwork bytes from
            # preflight. Never fetch photos or redraw a second time after the
            # decision, which could change the card or hit a transient API.
            setattr(pick,"_verified_owner_png",bytes(result))
            accepted.append(pick)
        else:
            blocked+=1
    return accepted,blocked
