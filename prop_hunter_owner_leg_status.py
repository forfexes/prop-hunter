"""Tiny, explicit verified leg-result marks for clean owner-original tickets.

A wager's outcome comes only from its already-settled stored result.
Unknown is never turned into a green tick, even if its model was confident.
"""
def leg_result_mark(index, result):
    try:
        n=int(index)
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid leg number") from exc
    if not 1 <= n <= 12:
        raise ValueError("Original Builder/Lottery supports up to 12 legs")
    text=str(result or "").strip().casefold()
    if "gewonnen" in text or text in {"won","win"}:
        return f"{n}✓", "won"
    if "verloren" in text or text in {"lost","loss"}:
        return f"{n}✕", "lost"
    if text in {"void","push"} or text.endswith(" · void") or text.endswith(" · push"):
        return f"{n}–", "void"
    return f"{n}.", "open"
