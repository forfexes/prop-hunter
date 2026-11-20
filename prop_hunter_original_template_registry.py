"""League-isolated locations for PROP HUNTER's four premium poster families.

The four user JPEG screenshots are present under card_templates/originals and
are reference images only, NOT reusable blank masters. A league may publish a
premium image only after that league's separate clean assets are approved.
NEVER redirect NFL, NHL, WNBA or MLB to NBA artwork as a silent fallback.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent / "card_templates"
FAMILIES = ("single", "ladder", "builder", "lottery")
# Distinct clean masters are REQUIRED for each league. Sharing hierarchy
# and layouts does not permit mixing official league logos or game assets.
SPORTS = {
    "NBA": "nba",
    "WNBA": "wnba",
    "NCAAB": "ncaab",
    "EUROLEAGUE": "euroleague",
    "NFL": "nfl",
    "NCAAF": "ncaaf",
    "NHL": "nhl",
    "MLB": "mlb",
}
# Legacy offline render functions pass generic sport names. Those generic
# directories are NOT approved league masters and never activate production.
LEGACY_GENERIC_FAMILIES = frozenset({"basketball", "football", "hockey", "baseball"})

ORIGINAL_REFERENCE_NAMES = {
    "single": "single.jpg",
    "ladder": "ladder.jpg",
    "builder": "builder.jpg",
    "lottery": "lottery.jpg",
}

def sport_family(name: str) -> str:
    """Resolve an exact league; NEVER map NFL/NHL/other leagues onto NBA."""
    key = str(name or "").strip().upper()
    if key in SPORTS:
        return SPORTS[key]
    generic = key.lower()
    if generic in LEGACY_GENERIC_FAMILIES:
        return generic
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
    """Four required NBA slots; other leagues require their OWN four slots."""
    return [template_location("NBA", family) for family in FAMILIES]


def league_required_templates(league: str) -> list[Path]:
    """All four explicit render-ready slots for a single requested league."""
    key = str(league or "").strip().upper()
    if key not in SPORTS:
        raise ValueError(f"An explicit supported league is required: {league!r}")
    return [template_location(key, family) for family in FAMILIES]


def league_is_ready(league: str) -> bool:
    """No publication unless all original-layout-derived clean masters exist."""
    return all(path.is_file() for path in league_required_templates(league))
