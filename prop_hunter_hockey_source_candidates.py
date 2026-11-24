"""Verified Swiss National League player/club source pages for image review.

Each URL is an official club player/roster or official club news page, not a
licensed bitmap. Never embed or repost the club's image just because a URL is
public. The manifest is editorial evidence for exact player+club matching
and a starting point for an independently approved, credited image license.
No scraping, guessing, picture synthesis, Telegram or Supabase writes.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceCandidate:
    player: str
    team: str
    url: str
    league: str = "SWISS_NL"
    image_license: str = "unverified"
    import_approved: bool = False


CANDIDATES = (
    SourceCandidate("Leonardo Genoni", "EV Zug",
                    "https://www.evz.ch/eissport/men/team/leonardo-genoni/"),
    SourceCandidate("Julien Sprunger", "Fribourg-Gottéron",
                    "https://www.gotteron.ch/de/news/detail?alias=Fribourg-Gotteron-prolonge-le-contrat-de-Julien-Sp&date=2024-12-20"),
    SourceCandidate("Philipp Kurashev", "Lausanne HC",
                    "https://lausannehc.ch/lions/23-philipp-kurashev"),
    SourceCandidate("Kevin Fey", "HC Ajoie",
                    "https://www.hc-ajoie.ch/fr/1ere-equipe/Players/View.html?PeriodID=77758&id=22050"),
    SourceCandidate("Luca Fazzini", "HC Lugano",
                    "https://www.hclugano.ch/luca_fazzini.php8"),
    SourceCandidate("Simon Hrubec", "ZSC Lions",
                    "https://www.zsclions.ch/1-mannschaft/team/spieler/30-hrubec/"),
    SourceCandidate("Markus Granlund", "Genève-Servette HC",
                    "https://www.gshc.ch/effectif/joueur/team/60-markus-granlund"),
    SourceCandidate("Rasmus Kupari", "HC Lugano",
                    "https://www.hclugano.ch/en/rasmus_kupari2.php8"),
    SourceCandidate("Jesper Frödén", "ZSC Lions",
                    "https://www.zsclions.ch/1-mannschaft/team/spieler/28-froeden/"),
    SourceCandidate("Miro Aaltonen", "SC Bern",
                    "https://www.scb.ch/national-league/mannschaft/spieler/detail/aaltonen-miro/"),
)


def _norm(value):
    import unicodedata
    import re
    normalized = unicodedata.normalize("NFKD", str(value or "").casefold())
    normalized = "".join(c for c in normalized if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", normalized)


def official_source(player, team, league):
    """Exact (player, team, competition) evidence; no fuzzy surname fallback."""
    if str(league or "").strip().upper() != "SWISS_NL":
        return None
    matches = [s for s in CANDIDATES
               if _norm(s.player) == _norm(player) and _norm(s.team) == _norm(team)]
    return matches[0] if len(matches) == 1 else None
