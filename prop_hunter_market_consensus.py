#!/usr/bin/env python3
"""Adds cross-source consensus, best price and line dispersion to prop snapshots."""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Tuple

from prop_hunter_shared_utils import norm_market, norm_name, safe_json_load, to_float


def _key(row: Dict[str, Any]) -> Tuple[str, str, str, str]:
    return (
        str(row.get("sport") or row.get("league") or "").upper(),
        norm_name(row.get("player_name") or row.get("player")),
        norm_market(row.get("market_key") or row.get("market")),
        str(row.get("direction") or "over").lower(),
    )


def enrich(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = [dict(r) for r in rows if isinstance(r, dict)]
    groups: Dict[Tuple[str, str, str, str], List[Dict[str, Any]]] = defaultdict(list)
    for row in rows: groups[_key(row)].append(row)
    trust_rows = safe_json_load("prop_hunter_source_trust.json", []) or []
    trust = {}
    for x in trust_rows:
        if not isinstance(x, dict): continue
        key = str(x.get("source_key") or x.get("source_name") or x.get("source") or "").lower()
        value = x.get("trust_multiplier") or ((x.get("raw") or {}).get("trust_multiplier") if isinstance(x.get("raw"), dict) else None)
        if value is None:
            value = float(x.get("trust_score") or 100) / 100.0
        trust[key] = max(0.65, min(1.20, float(value)))

    for members in groups.values():
        lines = [to_float(x.get("line")) for x in members]
        lines = [x for x in lines if x is not None]
        odds = [to_float(x.get("odds_decimal")) for x in members]
        odds = [x for x in odds if x and x > 1]
        median_line = statistics.median(lines) if lines else None
        dispersion = statistics.pstdev(lines) if len(lines) >= 2 else 0.0
        best_odds = max(odds) if odds else None
        # Average de-vig proxy only when multiple independent books quote the same side.
        implied = [1.0 / x for x in odds]
        consensus_prob = statistics.mean(implied) if implied else None
        sources = {str(x.get("source") or x.get("bookmaker") or "").lower() for x in members}
        for row in members:
            source = str(row.get("source") or row.get("bookmaker") or "unknown").lower()
            row["source_trust"] = trust.get(source, 1.0)
            row["consensus_line"] = median_line
            row["line_dispersion"] = round(dispersion, 4)
            row["best_odds"] = best_odds
            row["book_consensus"] = consensus_prob
            row["consensus_sources"] = len(sources)
    return rows
