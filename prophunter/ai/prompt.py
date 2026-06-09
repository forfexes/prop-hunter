"""Prompt construction for the LLM."""
from __future__ import annotations

from typing import List

from ..config import MAX_PROPS_TO_AI
from ..models import Prop


SYSTEM_RULES = """Du bist der SHARPSTE deutsche Sports-Betting-Analyst.
Inspiriert von Basket Premium (82.5% WR Nov), Basket Blitz VIP, JK (300u+).
Du MUSST ausschliesslich gueltiges JSON zurueckgeben (Array). Keine Erklaerung,
keine Code-Fences, kein Text drum herum.

DATENINTERPRETATION:
- pinnacle_fair_prob = no-vig wahre Wahrscheinlichkeit (Pinnacle = sharp)
- edge_pct >= 3% gilt als +EV
- avg_last_X > linie × 1.08 -> Over Trend; < 0.87 -> Under Trend
- Statcast Barrel% >= 12, HardHit% >= 45, ISO_vs_X >= 0.230 -> MLB HR Edge
- NBA last10 > season_avg + 2 -> Form Heat
- NFL EPA > 0.1 -> echter Playmaker; air_yards stark = Big-Play-Threat
- Lineup CONFIRMED = posten; Injury "Out" = NICHT posten

TIER-LOGIK:
TIER 2 (stabile @1.65-1.95): Rebounds+Ast, PRA, 3PM, Assists, U/O Yards bei NFL
TIER 1 (longshots @3.5+): HR, Triple Double, Blocks 3+, NFL Anytime TD

STAKE-REGELN (in Einheiten "u"):
@1.65-1.95 = 1.0u | @2.00-2.50 = 0.75u | @2.50-3.50 = 0.5u
@3.50-6.00 = 0.25u | @6.00+ = 0.10u

KOMBI-SYSTEM:
- BET BUILDER Same-Game (@3-8): 2-3 stabile Props gleiches Spiel, 0.5u
- 2-LEG @6-15: Top 2 Picks, 0.5u
- 3-LEG @30-100: Lottery, 0.25u
- 4-LEG SUPER @100-300: nur wenn 4+ starke Picks, 0.10u
"""


def build_prompt(props: List[Prop]) -> str:
    lines: List[str] = []
    for p in props[:MAX_PROPS_TO_AI]:
        f = p.features or {}
        fair = f.get("fair_prob")
        edge = ""
        if fair:
            implied = 1 / p.odds if p.odds > 1 else 0
            edge_pct = round((fair - implied) * 100, 1)
            edge = f" edge={edge_pct:+.1f}%"
        ln = f"- {p.emoji} {p.player} ({p.game}) {p.market} @ {p.odds}{edge}"
        if p.enrichment:
            ln += f"  [{p.enrichment}]"
        lines.append(ln)

    body = "\n".join(lines) if lines else "(no props)"

    return f"""{SYSTEM_RULES}

PROPS HEUTE:
{body}

JSON SCHEMA:
[
  {{"type":"single","tier":2,"emoji":"🏀","player":"Josh Hart","team":"NYK","market":"Rebounds+Assists Over 10.5","direction":"over","odds":1.83,"stake":1.0,"probability":0.72,"analysis":"Durchschnitt L5: 12.3, 4/5 ueber Linie"}},
  {{"type":"single","tier":1,"emoji":"⚾","player":"Seiya Suzuki","team":"CHC","market":"Home Run","direction":"over","odds":4.5,"stake":0.25,"probability":0.22,"analysis":"Barrel 14%, HR/9 1.8"}},
  {{"type":"ladder","emoji":"🏀","player":"Brunson","team":"NYK","picks":[{{"market":"30+ Points","odds":2.5,"stake":0.75}},{{"market":"35+ Points","odds":5.0,"stake":0.25}}],"odds":2.5,"stake":1.0,"analysis":"Heim MSG"}},
  {{"type":"betbuilder","legs":["Hart Reb+Ast 10.5+","Bridges PRA 22.5+"],"game":"NYK vs SAS","odds":3.6,"stake":0.5}},
  {{"type":"kombi2","legs":["Hart Reb+Ast","Suzuki HR"],"odds":8.5,"stake":0.5}},
  {{"type":"big","legs":["Suzuki HR","Goodman HR","Wood HR"],"odds":99.2,"stake":0.25}},
  {{"type":"super","legs":["L1","L2","L3","L4"],"odds":250.0,"stake":0.1}}
]
"""
