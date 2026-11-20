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
    from prop_hunter_original_compositor import original_card
    family = key.rsplit("_", 1)[0]
    if family not in ("single", "ladder", "builder"):
        raise ValueError("Owner original release is not approved for this family")
    if len(teams) != 2 or any(not team or logo is None
                              for team,logo in teams):
        raise ValueError("Owner original must show two genuine NBA teams")
    if not (BASE / (family + ".png")).is_file():
        raise ValueError("Owner original clean plate not approved")
    if family == "ladder" and not 2 <= len(rows) <= 5:
        raise ValueError("Original Ladder accepts one athlete with 2-5 rungs")
    if family == "builder" and not 2 <= len(rows) <= 6:
        raise ValueError("Original Builder accepts 2-6 verified athletes")
    dt = datetime.strptime(values["date"], "%d.%m.%Y")
    if not values.get("time"):
        raise ValueError("Verified NBA start time missing")
    source = f"{teams[0][0]} vs {teams[1][0]}"
    when = f"{WD[dt.weekday()]} {dt:%d.%m}. · {values['time']}"
    subtitle = source + " · " + when
    stake = values.get("stake")
    footer = "Quote " + (values.get("total_odds")
             or values.get("odds") or "")
    if stake:
        footer += " · Einsatz " + str(stake)
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
        })
    if family == "ladder":
        if len({r["name"].casefold() for r in labels}) != 1:
            raise ValueError("Original Ladder cannot mix athletes")
    return original_card(family, family.upper(), subtitle,"NBA",teams,
                         labels,footer,values.get("settlement") or "OFFEN")
