"""Explicit mapping from each PROP HUNTER sport to the user's four ORIGINAL poster layouts.

These paths are a contract, not a claim that the user-provided JPGs have been
uploaded.  Only render-ready artwork with editable data slots can be enabled.
A user screenshot containing prefilled players/odds is a reference/master,
not a safe template for directly overprinting changing picks.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent / "card_templates"
FAMILIES = ("single", "ladder", "builder", "lottery")
# All leagues use the SAME four original NBA layouts. Do not branch by sport.
# Actual NHL/NFL/WNBA player photos, crests and labels are dynamic overlays.
SPORTS = {
    "NBA": "basketball",
    "WNBA": "basketball",
    "NCAAB": "basketball",
    "EUROLEAGUE": "basketball",
    "NFL": "basketball",
    "NCAAF": "basketball",
    "NHL": "basketball",
    "MLB": "basketball",
}

ORIGINAL_REFERENCE_NAMES = {
    "single": "1000114998.jpg",
    "ladder": "1000114995.jpg",
    "builder": "1000114996.jpg",
    "lottery": "1000114997.jpg",
}

def sport_family(name: str) -> str:
    """All supported leagues and legacy sport names select NBA original artwork."""
    key = str(name or "").strip().upper()
    if key in SPORTS or key.lower() in ("basketball", "football", "hockey", "baseball", "wnba"):
        return "basketball"
    raise ValueError(f"Unsupported sport: {name!r}")

def poster_family(kind: str) -> str:
    kind = str(kind or "").lower()
    if kind in ("big", "super", "lottery"):
        return "lottery"
    if kind in ("betbuilder", "builder", "combo", "kombi", "cross", "same_game"):
        return "builder"
    if kind in FAMILIES:
        return kind
    raise ValueError(f"Unsupported poster family: {kind!r}")

def template_location(sport: str, kind: str) -> Path:
    """Expected slot-cleaned derived template; no fallback to a copied screenshot."""
    return ROOT / "render_ready" / sport_family(sport) / (poster_family(kind) + ".webp")

def available_template(sport: str, kind: str) -> Path | None:
    p = template_location(sport, kind)
    return p if p.is_file() else None

def all_required_templates() -> list[Path]:
    """Exactly FOUR images, shared by NBA, NHL, NFL, WNBA, MLB, etc."""
    return [template_location("NBA", family) for family in FAMILIES]
