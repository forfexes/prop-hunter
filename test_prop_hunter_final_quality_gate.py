"""No low-odds / weak-model NBA rescue pick may bypass Telegram preflight."""
from io import BytesIO
from types import SimpleNamespace as N
from unittest.mock import patch

from PIL import Image

from prop_hunter_image_publication_gate import (
    filter_verified_nba_images, owner_single_quality,
)

def single(price=1.85, prob=.72, edge=10.0):
    return N(type="single", player="TEST NO NETWORK", sport="NBA",
             source_sport="NBA", odds=price, probability=prob,
             edge_pct=edge, leg_details=[], features={})

assert owner_single_quality(single()) == (True, "premium_single_minimums_passed")
for candidate, reason in (
    (single(price=1.27), "single_odds_outside_1_70_to_3_00"),
    (single(price=1.69), "single_odds_outside_1_70_to_3_00"),
    (single(price=3.01), "single_odds_outside_1_70_to_3_00"),
    (single(prob=.61), "single_probability_below_67_percent"),
    (single(prob=.66), "single_probability_below_67_percent"),
    (single(edge=7.99), "single_edge_below_8pp"),
    (single(prob=None), "single_minimums_missing_observed_model"),
    (single(edge=None), "single_minimums_missing_observed_model"),
    (single(price=float("nan")), "single_minimums_nonfinite"),
    (single(price=float("inf")), "single_minimums_nonfinite"),
):
    assert owner_single_quality(candidate) == (False, reason), reason

buf = BytesIO()
Image.new("RGB", (1080, 1500), (7, 24, 52)).save(buf, "PNG")
PNG = buf.getvalue()

class Cards:
    called = []
    @staticmethod
    def league_of(sport):
        return ("basketball", "nba") if sport == "NBA" else None
    @staticmethod
    def build_for_pick(pick):
        Cards.called.append(pick.odds)
        return PNG

good = single()
bad = [single(price=1.27),single(prob=.61),single(edge=7)]
with patch.dict("os.environ", {"PH_ENFORCE_OWNER_QUALITY":"1"}):
    allowed, blocked = filter_verified_nba_images(bad + [good], Cards())
    assert allowed == [good], allowed
    assert blocked == len(bad), blocked
    assert Cards.called == [1.85], Cards.called
    assert all(not hasattr(p, "_verified_owner_png") for p in bad)
print("OWNER_LAST_MILE_1_70_3_00_67_PERCENT_8PP_GATE_PASSED")
