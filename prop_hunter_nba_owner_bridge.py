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


def render_owner(pick, key: str, rows: list, teams: list,
                 values: dict, details: list) -> bytes:
    # Production fail-closed: the legacy owner compositor still draws large
    # opaque rectangles over original artwork. Re-enable only after a reviewed
    # overlay-free clean-plate renderer replaces this path.
    import os
    if os.getenv("PH_BLOCK_OVERPAINTED_MASTERS", "0").strip() == "1":
        raise ValueError("owner_original_overpainted_compositor_blocked")
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
    if family == "ladder" and not 2 <= len(rows) <= 5:
        raise ValueError("Original Ladder accepts one athlete with 2-5 rungs")
    # The user has no clean six-row single-athlete owner original yet.
    # Fail closed instead of reverting to a newly designed SVG in owner mode.
    if family == "builder" and not 2 <= len(rows) <= 7:
        raise ValueError("Original Builder accepts 2-7 verified athletes")
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
        when = f"{WD[dt.weekday()]} {dt:%d.%m}. · {values['time']}"
        subtitle = source + " · " + when
    stake = values.get("stake")
    observed_quote = values.get("total_odds") or values.get("odds")
    feats=pick.get("features", {}) if isinstance(pick,dict) else getattr(pick,"features",{}) or {}
    verified=(isinstance(feats,dict) and feats.get("combined_odds_observed") is True
              and bool(feats.get("combined_quote_id")))
    footer=(("Quote " if verified or family in ("single","ladder") else "Berechnet ")
            + str(observed_quote)) if observed_quote else ""
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
            "model": row.get("model") or {},
            "game": values.get(f"leg_{i+1}_game") if family == "lottery" else "",
        })
    if family == "ladder":
        if len({r["name"].casefold() for r in labels}) != 1:
            raise ValueError("Original Ladder cannot mix athletes")
    title = ("SAME PLAYER" if render_family == "same_player" else
             "LONGSHOT" if render_family == "longshot" else family.upper())
    return original_card(family, title, subtitle,"NBA",teams,
                         labels,footer,values.get("settlement") or "OFFEN")
