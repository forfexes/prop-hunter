"""Regression for the Nov-22 empty-card failure: NBA originals should not
be squeezed out of the 18-tip rescue window by unapproved NFL photos.

This test is offline, deterministic and cannot send Telegram cards.
"""
from types import SimpleNamespace as N
from unittest.mock import patch

from prop_hunter_owner_rescue_select import (
    owner_only_mode, select_publishable_owner_rescue,
)


def pick(sport, odds=1.85, probability=.72, edge_pct=12):
    return N(type="single", source_sport=sport, odds=odds,
             probability=probability, edge_pct=edge_pct)

nfl = [pick("NFL", odds=1.77, probability=.84, edge_pct=16) for _ in range(26)]
nba = [pick("NBA", odds=1.83, probability=.71, edge_pct=10) for _ in range(4)]
weak = [pick("NBA", odds=1.27),
        pick("NBA", probability=.61),
        pick("NBA", edge_pct=6.0),
        pick("NBA", odds=float("nan"))]
input_pool = nfl + nba + weak
env = {
    "PH_OWNER_APPROVED_ALL_SPORTS": "1",
    "PH_NBA_OWNER_ORIGINALS": "1",
    "PH_ENFORCE_OWNER_QUALITY": "1",
}
with patch.dict("os.environ", env):
    assert owner_only_mode()
    pool, stats = select_publishable_owner_rescue(input_pool)
    assert pool == nba
    assert len(pool) == 4
    assert stats["blocked"]["unapproved_league"] == 26
    assert stats["retained"] == 4
    assert stats["blocked"]["single_odds_outside_1_70_to_3_00"] == 1
    assert stats["blocked"]["single_probability_below_67_percent"] == 1
    assert stats["blocked"]["single_edge_below_8pp"] == 1
    assert stats["blocked"]["single_minimums_nonfinite"] == 1
    assert len(input_pool) == 34
    assert all(isinstance(item, N) for item in input_pool)

for disabled in ("PH_ENFORCE_OWNER_QUALITY", "PH_OWNER_APPROVED_ALL_SPORTS",
                 "PH_NBA_OWNER_ORIGINALS"):
    with patch.dict("os.environ", {**env, disabled: "0"}):
        retained, stats = select_publishable_owner_rescue(input_pool)
        assert retained == input_pool
        assert stats["mode"] == "all_sports"

with patch.dict("os.environ", env):
    assert select_publishable_owner_rescue([])[0] == []
    assert select_publishable_owner_rescue([])[1]["considered"] == 0
print("SOURCE_RESCUE_NBA_ORIGINAL_FIRST_NO_UNAPPROVED_PHOTO_PASS")
