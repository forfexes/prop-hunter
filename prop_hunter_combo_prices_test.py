"""Multi-sport combo pricing: no missing-total-quote exclusion or fake profit."""
from copy import deepcopy
from types import SimpleNamespace
from prop_hunter_combo_prices import (
    calculated_combo_odds, prepare_calculated_combo, publishable_extra,
    unpriced_sgp, invalidate_unpriced_combo,
)

for sport in ("NBA", "NFL", "NHL", "MLB", "WNBA", "EUROLEAGUE", "SOCCER"):
    for kind in ("betbuilder", "combo", "lottery", "big", "super"):
        legs=[
            dict(player="PLAYER ONE",market="shots",odds=1.25,game="A vs B"),
            dict(player="PLAYER TWO",market="shots",odds=1.25,game="A vs B"),
            dict(player="PLAYER THREE",market="shots",odds=1.28,game="A vs B"),
            dict(player="PLAYER FOUR",market="shots",odds=1.33,game="A vs B"),
            dict(player="PLAYER FIVE",market="shots",odds=1.33,game="A vs B"),
        ]
        p=dict(type=kind,sport=sport,leg_details=legs,odds=None,features={})
        assert not publishable_extra(p), ("unbookable total blocked",sport,kind)
        assert round(calculated_combo_odds(p),2)==3.54
        prepare_calculated_combo(p)
        assert round(p["odds"],2)==3.54
        assert p["features"]["combined_odds_observed"] is False
        assert p["features"]["calculated_combined_odds"]>3.5
        assert invalidate_unpriced_combo(p), "derived same-game payout must be invalidated"
        assert p["quote_invalidated"] is True
        assert p["result"]=="withdrawn" and p["profit"] is None
        assert unpriced_sgp(p), "same-game estimated price must be flagged"

verified=dict(type="betbuilder",leg_details=[
    dict(odds=1.8,game="A vs B"),dict(odds=1.9,game="C vs D")],
    odds=3.25,features=dict(combined_odds_observed=True,combined_quote_id="book-123"))
prepare_calculated_combo(verified)
assert verified["odds"]==3.25, "observed combined ticket is authoritative"
assert publishable_extra(verified)
assert publishable_extra(dict(type="lottery",odds=3.25,
    features=dict(combined_odds_observed=True,combined_quote_id="book-321")))

cross=dict(type="lottery",leg_details=[
    dict(odds=1.8,game="A vs B"),dict(odds=1.9,game="C vs D")],features={})
assert not publishable_extra(cross) and not unpriced_sgp(cross)
assert round(calculated_combo_odds(cross),2)==3.42
assert not publishable_extra(dict(type="lottery",leg_details=[
    dict(odds=1.8),dict(odds=None)]))
assert not publishable_extra(dict(type="lottery",leg_details=[dict(odds=1.8)]))
assert not publishable_extra(dict(type="lottery",odds=4.2,
    features=dict(combined_odds_observed=True,combined_quote_id="   ")))
assert not publishable_extra(dict(type="betbuilder",odds=4.2,
    features=dict(combined_odds_observed=False,combined_quote_id="book-123")))
assert not publishable_extra(dict(type="lottery",odds=float("nan"),
    features=dict(combined_odds_observed=True,combined_quote_id="ticket")))
assert not publishable_extra(dict(type="lottery",odds=None,
    features=dict(combined_odds_observed=True,combined_quote_id="ticket")))
assert publishable_extra(dict(type="single",odds=1.8))
assert publishable_extra(dict(type="ladder",odds=1.8))

# Preserve already-withdrawn historical records; no artificial resurrection.
old=dict(type="betbuilder",quote_invalidated=True,result="withdrawn",
         features=dict(price_type="derived_builder"),
         leg_details=[dict(odds=1.8,game="A"),dict(odds=1.9,game="A")])
before=deepcopy(old)
assert not invalidate_unpriced_combo(old) and old==before
# Event identity must normalize whitespace consistently even when prices
# are missing; otherwise a repeated SAME game can be mislabeled CROSS-game.
from prop_hunter_combo_prices import publishable_extra_reason
same_unpriced = dict(type="lottery", features={}, leg_details=[
    dict(game="LAL vs BOS", odds=1.8),
    dict(game="LAL   vs   BOS", odds=None),
])
cross_unpriced = dict(type="lottery", features={}, leg_details=[
    dict(game="LAL vs BOS", odds=1.8),
    dict(game="NYK vs MIA", odds=None),
])
assert publishable_extra_reason(same_unpriced) == "same_game_missing_confirmed_quote"
assert publishable_extra_reason(cross_unpriced) == "cross_game_missing_confirmed_quote"


# The nominal pick type must not let a disguised multi-leg ticket bypass the
# global price gate in any sport. A real Ladder is ONE player/one market with
# separately observed finite odds for every threshold.
for sport in ("NBA", "NFL", "NHL", "MLB", "WNBA", "EUROLEAGUE", "SOCCER"):
    two_players=[
        dict(player="PLAYER A",market="Points Over 20.5",odds=1.72,game="A vs B"),
        dict(player="PLAYER B",market="Points Over 25.5",odds=1.83,game="A vs B"),
    ]
    for wrong_type in ("single", "longshot", "ladder"):
        fake=dict(type=wrong_type, sport=sport, player="PLAYER A",
                  odds=3.14, leg_details=two_players,
                  features={"combined_odds_observed":True,
                            "combined_quote_id":"REAL-OTHER-TICKET"})
        assert not publishable_extra(fake), (sport,wrong_type)
    # Alternative serialized containers cannot evade the same check.
    assert not publishable_extra(dict(type="single",sport=sport,odds=3.14,
                                      picks=two_players))
    same_player=[
        dict(player="PLAYER A",market="Blocks Under 2.5",odds=1.52),
        dict(player="PLAYER A",market="Blocks Under 1.5",odds=2.43),
    ]
    assert publishable_extra(dict(type="ladder",sport=sport,
                                  player="PLAYER A",leg_details=same_player))
    assert not publishable_extra(dict(type="ladder",sport=sport,
        player="PLAYER A",leg_details=[same_player[0],
        dict(same_player[1],market="Rebounds Under 1.5")]))
    for bad in (None,float("nan"),float("inf"),1.0):
        assert not publishable_extra(dict(type="ladder",sport=sport,
            player="PLAYER A",leg_details=[same_player[0],
                                           dict(same_player[1],odds=bad)]))
    assert not publishable_extra(dict(type="ladder",sport=sport,
        leg_details=[dict(same_player[0],player=""),
                     dict(same_player[1],player="")]))
print("ALL-SPORT DISGUISED MULTI-LEG / SINGLE-PLAYER LADDER GATE PASSED")

print("MULTISPORT COMBO QUOTE REGRESSIONS PASSED")
