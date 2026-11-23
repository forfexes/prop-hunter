"""Render approved owner-original NBA PNG cards from fully verified adapter data.

Not a fallback renderer. Missing approved masters, authentic photos, observed
odds or same-fixture context fails closed; no synthetic data and no Telegram
calls. The 52 SVG masters remain available for other formats until separately
approved for the owner's original visual design.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PIL import Image

BASE = Path(__file__).resolve().parent / "card_templates" / "approved"
WD = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")


def user_single_original_enabled(pick) -> bool:
    """Select the same original for first Telegram send and later settlement.

    Fresh picks follow the explicit rollout flag. A saved Telegram image_pick
    carries an immutable per-card bool; a historical False prevents unrelated
    691px cards from being silently converted to the new 512px artwork.
    """
    marker = (pick.get("_owner_single_master_20261122")
              if isinstance(pick, dict)
              else getattr(pick, "_owner_single_master_20261122", None))
    if type(marker) is bool:
        return marker
    # Historical Telegram snapshots already have an earlier verified owner
    # source marker. Their missing 20261122 flag means the OLD 691px master,
    # even when fresh Singles have moved to the new source globally.
    if (isinstance(pick,dict)
            and pick.get("_owner_layered_original_v1") is True):
        return False
    import os
    return os.getenv("PH_NBA_USER_SINGLE_20261122", "0") == "1"



def _layered_owner_release_ready() -> bool:
    """Release only if all four clean owner-derived plates are current.

    Unmodified user JPEGs are references. Legacy screenshot cover-ups remain
    forbidden in real Telegram, even after a separate layered release.
    """
    root = BASE.parent
    for family in ("single", "ladder", "builder", "lottery"):
        approved = BASE / (family + ".png")
        cleaned = root / "cleaned" / (family + ".png")
        if not (approved.is_file() and cleaned.is_file()):
            return False
        if approved.read_bytes() != cleaned.read_bytes():
            return False
    return True


def render_owner(pick, key: str, rows: list, teams: list,
                 values: dict, details: list) -> bytes:
    # Production fail-closed: the legacy owner compositor still draws large
    # opaque rectangles over original artwork. Re-enable only after a reviewed
    # overlay-free clean-plate renderer replaces this path.
    import os
    if os.getenv("PH_BLOCK_OVERPAINTED_MASTERS", "0").strip() == "1":
        # Keep old overpaint fully blocked. A separate NBA-only production
        # release can use only the approved source-derived layered renderer.
        if (os.getenv("PH_ALLOW_VERIFIED_LAYERED_OWNER", "0").strip() != "1"
                or os.getenv("PH_NBA_OWNER_ORIGINALS", "0").strip() != "1"):
            raise ValueError("owner_original_overpainted_compositor_blocked")
        if not _layered_owner_release_ready():
            raise ValueError("owner_layered_clean_plates_not_ready")
    from prop_hunter_original_compositor import original_card
    # The master key is the approved market identifier, not necessarily
    # family + one numeric suffix. Single-market names may contain underscores.
    render_family = "single" if key.startswith("single_") else key.rsplit("_", 1)[0]
    # PROP HUNTER has exactly four user originals. Cross-game Combo/ACCA
    # are a data variant of the user's LOTTERY original, not a generic
    # fallback or an illicit reuse of an NBA single-match Builder.
    family = ("lottery" if render_family in ("combo", "cross_game")
              else "ladder" if render_family == "same_player"
              else "single" if render_family == "longshot"
              else render_family)
    if family not in ("single", "ladder", "builder", "lottery"):
        raise ValueError("Owner original release is not approved for this family")
    if family != "lottery" and (len(teams) != 2 or any(
            not team or logo is None for team,logo in teams)):
        raise ValueError("Owner original must show two genuine NBA teams")
    if family == "lottery" and not 2 <= len(rows) <= 12:
        raise ValueError("Original Lottery supports 2-12 verified selections")
    if not (BASE / (family + ".png")).is_file():
        raise ValueError("Owner original clean plate not approved")
    if family == "ladder" and not 2 <= len(rows) <= 6:
        raise ValueError("Original Ladder or Same Player requires one athlete with 2-6 verified legs")
    # Six-row Ladder uses only an owner-source-derived EMPTY stadium extension.
    # Fail closed instead of reverting to a newly designed SVG in owner mode.
    if family == "builder" and not 2 <= len(rows) <= 10:
        raise ValueError("Original Builder accepts 2-10 verified athletes")
    if family == "lottery":
        # No fictitious single date/opponent for multi-game tickets. Exact
        # game and tipoff are printed for EVERY individual leg instead.
        subtitle=f"NBA · {len(rows)} SPIELE"
        teams=[]
    else:
        dt = datetime.strptime(values["date"], "%d.%m.%Y")
        if not values.get("time"):
            raise ValueError("Verified NBA start time missing")
        source = f"{teams[0][0]} vs {teams[1][0]}"
        when = f"{WD[dt.weekday()]} {dt:%d.%m.%Y} · {values['time']}"
        subtitle = source + " · " + when
    stake = values.get("stake")
    observed_quote = values.get("total_odds") or values.get("odds")
    feats=pick.get("features", {}) if isinstance(pick,dict) else getattr(pick,"features",{}) or {}
    from prop_hunter_combo_prices import confirmed_ticket
    verified=confirmed_ticket(pick)
    # A multiplied component-odds product is not a price a user can
    # actually book. Every Builder, Lottery, cross-game or same-player
    # multi-stat card MUST carry a separately observed bookmaker ticket.
    # A regular one-athlete LADDER instead displays independently observed
    # rung prices and does not claim a combined booking price.
    combined_ticket=(family in ("builder","lottery")
                     or render_family=="same_player")
    if combined_ticket and not verified:
        raise ValueError("Observed bookmaker combined ticket ID required; calculated quote forbidden")
    if combined_ticket and not observed_quote:
        raise ValueError("Observed bookmaker combined ticket price missing")
    footer=("Quote "+str(observed_quote)) if observed_quote and (
        verified or not combined_ticket) else ""
    if stake:
        footer += (" · " if footer else "") + "Einsatz " + str(stake)
    labels=[]
    for i, row in enumerate(rows):
        photo=row.get("photo")
        if not isinstance(photo,Image.Image):
            raise ValueError(f"Authentic athlete photo missing for leg {i+1}")
        price = values.get("odds") if family == "single" else values.get(
            f"leg_{i+1}_odds")
        if not price or not str(row.get("name") or "").strip():
            raise ValueError(f"Verified athlete/price missing for leg {i+1}")
        labels.append({
            "name": str(row["name"]), "photo": photo,
            "label": str(row.get("label") or "").strip(),
            "odds": price, "form": row.get("form") or "",
            # Critical: the result of EACH Ladder/Builder/ Lottery leg is
            # settled in its ORIGINAL Telegram photo. Without this field
            # the clean original renderer gets a blank result for every rung.
            "result": str(row.get("result") or "").strip(),
            "model": row.get("model") or {},
            "game": values.get(f"leg_{i+1}_game") if family == "lottery" else "",
        })
    if family == "ladder":
        if len({r["name"].casefold() for r in labels}) != 1:
            raise ValueError("Original Ladder cannot mix athletes")
    title = ("SAME PLAYER" if render_family == "same_player" else
             "LONGSHOT" if render_family == "longshot" else family.upper())
    from prop_hunter_telegram_safe_zone import append_owner_margin
    # Telegram overlays its message time/edited status at bottom right.
    # Preserve the entire approved owner poster; append an EMPTY scanline-only
    # metadata margin AFTER rendering (never cover original text or artwork).
    # New user's actual 22.11.26 SINGLE is an independent, 512px source.
    # Unlike the older stadium master, it has different field geometry.
    # Never reuse the old text coordinates or silently switch to a substitute.
    if (family == "single" and title == "SINGLE"
            and user_single_original_enabled(pick)):
        from prop_hunter_owner_supplied_single import render as render_supplied_single
        if len(labels) != 1:
            raise ValueError("User original SINGLE requires one actual athlete")
        owner_png = render_supplied_single(
            title=title, subtitle=subtitle, teams=teams, row=labels[0],
            footer=footer, settlement=values.get("settlement") or "OFFEN")
    else:
        owner_png = original_card(family, title, subtitle,"NBA",teams,
                                  labels,footer,values.get("settlement") or "OFFEN")
    return append_owner_margin(owner_png)
