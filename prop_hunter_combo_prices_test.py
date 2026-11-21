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
        assert publishable_extra(p), (sport,kind)
        assert round(calculated_combo_odds(p),2)==3.54
        prepare_calculated_combo(p)
        assert round(p["odds"],2)==3.54
        assert p["features"]["combined_odds_observed"] is False
        assert p["features"]["calculated_combined_odds"]>3.5
        assert not invalidate_unpriced_combo(p), "missing quote alone may not withdraw"
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
assert publishable_extra(cross) and not unpriced_sgp(cross)
assert round(calculated_combo_odds(cross),2)==3.42
assert not publishable_extra(dict(type="lottery",leg_details=[
    dict(odds=1.8),dict(odds=None)]))
assert not publishable_extra(dict(type="lottery",leg_details=[dict(odds=1.8)]))
assert publishable_extra(dict(type="single",odds=1.8))
assert publishable_extra(dict(type="ladder",odds=1.8))

# Preserve already-withdrawn historical records; no artificial resurrection.
old=dict(type="betbuilder",quote_invalidated=True,result="withdrawn",
         features=dict(price_type="derived_builder"),
         leg_details=[dict(odds=1.8,game="A"),dict(odds=1.9,game="A")])
before=deepcopy(old)
assert not invalidate_unpriced_combo(old) and old==before
print("MULTISPORT COMBO QUOTE REGRESSIONS PASSED")
