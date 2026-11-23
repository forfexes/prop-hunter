"""Shared normal-market confidence display formula for owner-original cards.

Matches the current PROPHUNTER core text _confidence_score for non-HR picks.
It derives ONLY from the observed pick's already-computed probability, edge,
and decimal bookmaker odds. It never invents any of those three inputs.
"""
from __future__ import annotations
import math


def normal_pick_confidence(probability, edge_pct, odds):
    try:
        probability=float(probability)
        edge_pct=float(edge_pct)
        odds=float(odds)
    except (ValueError, TypeError, OverflowError):
        return None
    if (not all(map(math.isfinite,(probability,edge_pct,odds))) or
            not 0<=probability<=1 or odds<=1):
        return None
    edge=max(0.0,edge_pct)
    penalty=max(0.0,odds-2.0)*3.0
    score=35.0+probability*50.0+min(edge,20.0)-penalty
    return int(max(1,min(99,round(score))))
