"""Consistent one-unit settlement and visible stakes for PROP HUNTER.

A Ladder is one ticket with several individually recorded positions: the
displayed rung stakes MUST sum to its total stake. Never invent betting prices.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def apply_flat_ticket_stake(ticket, amount: float, *, lottery_amount: float = 0.10):
    """Mutate a validated Pick before image preflight, text and DB persistence.

    Every standard ticket totals the configured flat unit. Lottery tickets
    remain explicitly low-risk. Each Ladder rung receives an exact 0.01u
    allocation, with any rounding cents assigned deterministically to the
    earliest rungs; no extra bankroll is quietly risked.
    """
    def cents(value):
        try:
            v = Decimal(str(value))
            if not v.is_finite() or not Decimal("0") < v <= Decimal("5"):
                raise ValueError("Invalid flat ticket stake")
            return int((v * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError("Invalid flat ticket stake") from exc

    get = lambda key, default=None: (
        ticket.get(key, default) if isinstance(ticket, dict)
        else getattr(ticket, key, default)
    )
    set_ = lambda obj, key, value: (
        obj.__setitem__(key, value) if isinstance(obj, dict)
        else setattr(obj, key, value)
    )
    kind = str(get("type", "") or "").lower()
    market = str(get("market", "") or "").lower()
    profile = str(get("profile", "") or "").lower()
    lottery = kind == "big" or any(
        "lottery" in part for part in (kind, market, profile)
    )
    total_cents = cents(lottery_amount if lottery else amount)
    if kind == "ladder":
        rungs = list(get("picks", []) or [])
        if not 2 <= len(rungs) <= 6 or total_cents < len(rungs):
            raise ValueError("Ladder requires 2-6 independently priced stakes")
        base, remainder = divmod(total_cents, len(rungs))
        for i, rung in enumerate(rungs):
            set_(rung, "stake", (base + (i < remainder)) / 100)
        assert round(sum(
            float(r.get("stake")) if isinstance(r, dict)
            else float(getattr(r, "stake")) for r in rungs
        ), 2) == total_cents / 100
    set_(ticket, "stake", total_cents / 100)
    return ticket
