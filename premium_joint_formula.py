"""Pure, offline formula engine for COMBO / BUILDER / LOTTERY.

An *indicative mathematical product* of leg odds is NOT an observed bookmaker
combined ticket. Never use it as realised profit or a bookable Telegram quote.

Independent legs:  P(all) = product(P_i).
Correlated legs:   P(all) = P(A) * P(B|A) * ... if conditionals are observed;
                   or jointly-observed successes / total sample.
Without dependence evidence: model fair odds / EV remain unknown.
"""
from __future__ import annotations
import math
import re


def _field(obj, key, default=None):
    return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)


def _positive_odds(value):
    try:
        x = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return x if math.isfinite(x) and 1.0 < x < 100000 else None


def _p(value):
    """Convert observed 0..1 probability or 0..100 percent to a fraction."""
    try:
        raw = str(value).strip()
        explicit_percent = raw.endswith("%")
        x = float(raw.rstrip("%").replace(",", "."))
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(x) or x < 0:
        return None
    if explicit_percent:
        return x / 100 if x <= 100 else None
    if x <= 1:
        return x
    return x / 100 if x <= 100 else None


def _fixture_key(leg):
    event_id = _field(leg, "event_id")
    if event_id is not None and str(event_id).strip():
        return "event:" + str(event_id).strip().casefold()
    game = _field(leg, "game") or _field(leg, "match")
    key = " ".join(str(game or "").lower().split())
    return "fixture:" + key if key else ""


def estimate_combo(legs, *, conditional_probabilities=None,
                   joint_observations=None, observed_ticket=None):
    """Compute labelled estimates only; never synthesise a bookmaker quote.

    observed_ticket optional {combined_odds_observed: True,
    combined_quote_id: nonempty, odds: positive finite}.
    conditional_probabilities: P(leg_2 | leg_1), ..., P(leg_n | earlier).
    joint_observations: {wins: int, total: int}, minimum 30 matched events.
    """
    legs = list(legs or [])
    if not 2 <= len(legs) <= 20:
        raise ValueError("Formula requires 2-20 real selections")
    prices = [_positive_odds(_field(leg, "odds")) for leg in legs]
    if any(x is None for x in prices):
        raise ValueError("Every leg needs a finite positive individual price")
    indicative = math.prod(prices)
    if not math.isfinite(indicative) or indicative >= 1000000000:
        raise ValueError("Indicative product exceeds safe numeric range")
    keys = [_fixture_key(leg) for leg in legs]
    if all(keys) and len(set(keys)) == len(keys):
        scope = "separate_games_independence_assumed"
    elif all(keys):
        scope = "shared_game_correlated"
    else:
        scope = "event_identity_unknown"
    verified_legs = all(
        _field(leg, "odds_observed") is True
        or _field(_field(leg, "features") or {}, "odds_observed") is True
        for leg in legs
    )
    probs = [_p(_field(leg, "model_probability",
                       _field(leg, "probability"))) for leg in legs]
    probability = None
    method = "insufficient_probability_or_dependence_data"
    if joint_observations is not None:
        w = _field(joint_observations, "wins")
        n = _field(joint_observations, "total")
        if not isinstance(w, int) or isinstance(w, bool) or not isinstance(n, int) or isinstance(n, bool) or n < 30 or not 0 <= w <= n:
            raise ValueError("Joint samples require >=30 paired observations and 0<=wins<=total")
        probability, method = w / n, "observed_joint_frequency"
    elif conditional_probabilities is not None:
        cond = [_p(p) for p in conditional_probabilities]
        if len(cond) != len(legs) - 1 or any(p is None for p in cond) or probs[0] is None:
            raise ValueError("Conditional model requires P(first) and N-1 verified conditional probabilities")
        probability = probs[0] * math.prod(cond)
        method = "chain_rule_observed_conditionals"
    elif scope == "separate_games_independence_assumed" and all(p is not None for p in probs):
        probability = math.prod(probs)
        method = "independence_assumption"
    actual_price = None
    if observed_ticket:
        verified = _field(observed_ticket, "combined_odds_observed") is True
        receipt = str(_field(observed_ticket, "combined_quote_id") or "").strip()
        odds = _positive_odds(_field(observed_ticket, "odds"))
        if verified and receipt and odds:
            actual_price = odds
    fair = 1 / probability if probability is not None and probability > 0 else None
    ev = (100 * (probability * actual_price - 1)
          if probability is not None and actual_price is not None else None)
    return {
        "leg_count": len(legs),
        "scope": scope,
        "indicative_leg_product": round(indicative, 4),
        "indicative_label": "BERECHNET – KEINE BUCHMACHERQUOTE",
        "individual_prices_observed": verified_legs,
        "joint_probability": probability,
        "joint_probability_method": method,
        "fair_model_odds": fair,
        "real_bookmaker_combined_odds": actual_price,
        "ev_percent_using_real_ticket_only": ev,
        "settle_as_bookmaker_ticket": actual_price is not None,
    }
