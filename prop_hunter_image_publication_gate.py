"""Preflight all NBA owner-original Telegram cards without dropping other picks.

Only source-verified original PNG cards may be published. Unknown images remain
unpublished (not silently replaced by text), and the history writer receives
only the actual eligible subset. No network calls except through supplied
image-card renderer; no Telegram or Supabase access.
"""
from __future__ import annotations

from io import BytesIO
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from PIL import Image


_PNG_MAGIC=bytes((137,80,78,71,13,10,26,10))



def owner_image_signature(pick):
    """Hash all ticket fields that can invalidate a pre-verified owner PNG.

    The fingerprint is intentionally strict: unknown changed state prevents
    reuse rather than risking stale bookmaker odds, lineups or players.
    """
    keys = (
        "type", "sport", "source_sport", "game", "commence_time", "date",
        "player", "market", "point", "direction", "odds", "stake",
        # A confirmed card may become stale even when its decimal odds do not.
        # The rendered probability, edge, identity and settlement all matter.
        "probability", "edge_pct", "confidence", "value", "model",
        "status", "result", "settlement", "settlement_status",
        "game_id", "event_id", "bookmaker", "odds_source",
        "combined_odds", "total_odds", "combined_quote_id",
        "combined_odds_observed", "home_team", "away_team",
        "leg_details", "ladder_legs", "legs", "picks", "features",
    )
    record = {}
    for key in keys:
        field = pick.get(key) if isinstance(pick,dict) else getattr(pick,key,None)
        if hasattr(field,"model_dump"):
            field=field.model_dump()
        record[key]=field
    record["approval_mode"]={
        "nba_owner":os.getenv("PH_NBA_OWNER_ORIGINALS","0"),
        "no_overpaint":os.getenv("PH_BLOCK_OVERPAINTED_MASTERS","0"),
        "layered_owner_release":os.getenv("PH_ALLOW_VERIFIED_LAYERED_OWNER","0"),
        "all_sports":os.getenv("PH_OWNER_APPROVED_ALL_SPORTS","0"),
        "pixel_qa":os.getenv("PH_OWNER_PIXEL_QA","0"),
        "quote_qa":os.getenv("PH_OWNER_QUOTE_QA","0"),
        "premium_quality":os.getenv("PH_ENFORCE_OWNER_QUALITY","0"),
    }
    raw=json.dumps(record,sort_keys=True,default=str,ensure_ascii=True,
                   allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _pick_value(pick, key, default=None):
    return pick.get(key, default) if isinstance(pick, dict) else getattr(pick, key, default)


def owner_single_quality(pick):
    """Final NBA Single minimums; rescue and AI picks share the SAME gate.

    Odds must be an observed bookmaker price (separate quote-provenance gate).
    Probability is 0..1 and edge_pct is in percentage POINTS, not a fraction.
    No unknown or missing forecast may be filled with fabricated statistics.
    """
    if str(_pick_value(pick, "type", "") or "").strip().lower() != "single":
        return True, "other_owner_family"
    try:
        odds = float(_pick_value(pick, "odds"))
        prob = float(_pick_value(pick, "probability"))
        edge = float(_pick_value(pick, "edge_pct"))
    except (TypeError, ValueError, OverflowError):
        return False, "single_minimums_missing_observed_model"
    if not (math.isfinite(odds) and math.isfinite(prob) and math.isfinite(edge)):
        return False, "single_minimums_nonfinite"
    if not 1.70 <= odds <= 3.00:
        return False, "single_odds_outside_1_70_to_3_00"
    if not 0.67 <= prob <= 1.0:
        return False, "single_probability_below_67_percent"
    if edge < 8.0:
        return False, "single_edge_below_8pp"
    return True, "premium_single_minimums_passed"


def pre_match_quote_provenance(pick):
    """Block stale pre-match prices and unlabeled sportsbook odds in live sends.

    Settlement photo editing intentionally uses its own historical safeguards;
    this test runs only immediately before NEW Telegram publication.
    """
    kind=str(_pick_value(pick, "type", "") or "").strip().lower()
    f=_pick_value(pick, "features", {}) or {}
    if not isinstance(f, dict):
        return False, "no_quote_provenance"
    # Single-leg prices have no combined ticket; demand a real bookmaker or
    # observed exchange source rather than treating a formula estimate as odds.
    if kind in ("single", "longshot"):
        observed=(f.get("odds_observed") is True or
                  (f.get("odds_observed") is None and
                   str(f.get("price_type") or "").lower()
                   in ("bookmaker", "observed", "exchange")))
        source=str(f.get("bookmaker") or f.get("source") or "").strip()
        if not observed or not source or source.lower() in (
            "synthetic", "model", "estimated", "calculated", "unknown"):
            return False, "single_missing_observed_bookmaker"
    try:
        price=float(_pick_value(pick, "odds"))
        if kind not in ("ladder",) and (not math.isfinite(price) or price <= 1):
            return False, "invalid_bookmaker_decimal_price"
    except (ValueError, TypeError, OverflowError):
        if kind != "ladder":
            return False, "invalid_bookmaker_decimal_price"
    details=list(_pick_value(pick, "leg_details", None) or [])
    if kind == "ladder" and not details:
        return False, "ladder_rungs_missing"
    scope=str(f.get("combo_scope") or "").lower()
    if scope == "cross_game":
        if len(details)<2:
            return False, "cross_game_leg_timestamps_missing"
        times=[_pick_value(leg, "commence_time") for leg in details]
    else:
        times=[(_pick_value(pick, "commence_time")
                or f.get("commence_time"))]
    now=datetime.now(timezone.utc)
    for value in times:
        if not value:
            return False, "kickoff_unverified"
        try:
            when=(value if isinstance(value,datetime) else
                  datetime.fromisoformat(str(value).replace("Z","+00:00")))
            if when.tzinfo is None or when.astimezone(timezone.utc) <= now:
                return False, "prematch_fixture_already_started"
        except (ValueError, TypeError, OverflowError):
            return False, "kickoff_invalid"
    return True, "observed_prematch_quote"


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
        for stale_attr in ("_verified_owner_png","_verified_owner_signature"):
            if hasattr(pick,stale_attr):
                try:
                    delattr(pick,stale_attr)
                except (AttributeError,TypeError):
                    blocked+=1
                    break
        else:
            pass
        if hasattr(pick,"_verified_owner_png") or hasattr(pick,"_verified_owner_signature"):
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
        if os.getenv("PH_ENFORCE_OWNER_QUALITY", "0").strip() == "1":
            qualified, reason = owner_single_quality(pick)
            if not qualified:
                print("OWNER_PREMIUM_QUALITY_BLOCKED reason=" + reason, flush=True)
                blocked += 1
                continue
        if os.getenv("PH_OWNER_QUOTE_QA", "0").strip() == "1":
            proven, reason=pre_match_quote_provenance(pick)
            if not proven:
                print("OWNER_QUOTE_PREFLIGHT_BLOCKED reason="+reason, flush=True)
                blocked+=1
                continue
        # A pick may be rechecked after bookmaker odds, lineups, photos or
        # ticket provenance changed. Invalidate an old successful preflight
        # before every new check. Otherwise a previously cached image could
        # be uploaded even after the updated pick is rejected.
        # Publishing a combined NBA ticket requires an actual observed
        # bookmaker price AND its ticket identifier. Multiplying authentic
        # single-leg odds is useful for offline analysis, but is not a
        # bookable parlay price and must never reach Telegram as a pick.
        # A single malformed athlete photo, empty source asset or rejected
        # owner render must never abort neighbouring valid picks in the batch.
        # Catch only expected image/validation failures; programmer defects
        # remain visible to CI rather than being silently swallowed.
        try:
            result=cards.build_for_pick(pick)
        except (ValueError, TypeError, OSError) as exc:
            print("OWNER_CARD_RENDER_BLOCKED reason=" + type(exc).__name__,
                  flush=True)
            blocked += 1
            continue
        if _valid_owner_png(result):
            # A structurally valid image is NOT sufficient. In owner release
            # mode, compare the real NBA original masthead pixel-for-pixel
            # against both the approved AND the latest cleaned source plate.
            # This refuses a stale master, an altered crown, and sample-image
            # overlays before any Telegram transport is attempted.
            if os.getenv("PH_OWNER_PIXEL_QA", "0").strip() == "1":
                from prop_hunter_owner_pixel_qa import owner_pixel_provenance
                passed, reason = owner_pixel_provenance(pick, result)
                if not passed:
                    print("OWNER_PIXEL_QA_BLOCKED reason=" + reason, flush=True)
                    blocked += 1
                    continue
            # Production will reuse the exact verified artwork bytes from
            # preflight. Never fetch photos or redraw a second time after the
            # decision, which could change the card or hit a transient API.
            try:
                signature=owner_image_signature(pick)
            except (TypeError,ValueError,OverflowError):
                blocked+=1
                continue
            setattr(pick,"_verified_owner_png",bytes(result))
            setattr(pick,"_verified_owner_signature",signature)
            accepted.append(pick)
        else:
            blocked+=1
    return accepted,blocked
