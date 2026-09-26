#!/usr/bin/env python3
"""Offline regression test for cross-game ACCA generation."""
from types import SimpleNamespace

from prop_hunter_acca_engine import cross_game_accas


class Pick(SimpleNamespace):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)


def single(player, game, odds=2.20, prob=0.55):
    p = Pick(
        type="single", category="verified_pool", tier=1, player=player, team="",
        emoji="🏈", market="Anytime Touchdown", direction="over", odds=odds,
        stake=.2, probability=prob, edge_pct=round((prob*odds-1)*100,1),
        ev=round(prob*odds-1,4), game=game,
        analysis="test",
    )
    p.point = 0.5
    p.sport = "NFL"
    p.features = {"odds_observed": True, "price_type": "bookmaker", "bookmaker": "bet365"}
    return p


def main():
    picks = [single("Player A", "A @ B"), single("Player C", "C @ D"), single("Player E", "E @ F")]
    accas = cross_game_accas(picks, [], Pick)
    assert accas, "expected cross-game ACCA"
    assert any((a.features or {}).get("combo_scope") == "cross_game" for a in accas)
    assert all(len({d["game"] for d in a.leg_details}) == len(a.leg_details) for a in accas)
    assert all((a.features or {}).get("price_type") == "derived_acca" for a in accas)

    same = [single("Player A", "A @ B"), single("Player C", "A @ B"), single("Player E", "A @ B")]
    assert cross_game_accas(same, [], Pick) == [], "same-game rows must not become ACCA"
    print("PROP HUNTER ACCA TEST: PASS")


if __name__ == "__main__":
    main()
