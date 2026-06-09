"""Kelly Criterion staking — conservative fractional Kelly."""
from __future__ import annotations

from ..config import KELLY_FRACTION, MAX_STAKE_UNITS, MIN_STAKE_UNITS


def kelly_stake(
    prob: float,
    decimal_odds: float,
    bankroll_units: float = 100.0,
    fraction: float = KELLY_FRACTION,
) -> float:
    if prob <= 0 or prob >= 1 or decimal_odds <= 1:
        return 0.0
    b = decimal_odds - 1
    q = 1 - prob
    f_star = (prob * b - q) / b
    if f_star <= 0:
        return 0.0
    stake = f_star * fraction * bankroll_units / 100.0
    return round(max(MIN_STAKE_UNITS, min(MAX_STAKE_UNITS, stake)), 2)


def stake_for_pick(prob: float | None, decimal_odds: float, ai_stake: float | None = None) -> float:
    if prob is None:
        return ai_stake if ai_stake is not None else 0.25
    kelly = kelly_stake(prob, decimal_odds)
    if ai_stake is None:
        return kelly or 0.25
    blend = round((kelly + ai_stake) / 2, 2)
    return min(blend, ai_stake)
