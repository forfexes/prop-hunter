"""De-vig / no-vig calculations and EV math."""
from __future__ import annotations

from typing import Optional


def implied_prob(decimal_odds: float) -> float:
    if decimal_odds <= 1.0:
        return 0.0
    return 1.0 / decimal_odds


def no_vig_two_way(side_odds: float, opp_odds: float) -> Optional[float]:
    if side_odds <= 1 or opp_odds <= 1:
        return None
    p1 = implied_prob(side_odds)
    p2 = implied_prob(opp_odds)
    total = p1 + p2
    if total <= 0:
        return None
    return p1 / total


def expected_value(prob: float, decimal_odds: float, stake: float = 1.0) -> float:
    return stake * (prob * (decimal_odds - 1) - (1 - prob))


def edge_percent(prob: float, decimal_odds: float) -> float:
    return prob - implied_prob(decimal_odds)
