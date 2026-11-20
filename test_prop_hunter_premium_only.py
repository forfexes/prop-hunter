"""Regression guard: no old design may be rendered by build_for_pick.

Run: python -m pytest -q test_prop_hunter_premium_only.py
"""
from types import SimpleNamespace
from unittest.mock import patch
import prop_hunter_image_cards as cards


def _pick(sport):
    return SimpleNamespace(type="single", player="Test Player", market="points",
                           direction="over", point=20.5, odds=1.85,
                           source_sport=sport, game="Home vs Away",
                           features={"bookmaker": "verified"}, leg_details=[])


def test_nba_failed_premium_never_uses_legacy_renderer():
    with patch.object(cards, "ON", True), \
         patch.object(cards, "player_photo", return_value=None), \
         patch.object(cards, "team_logo", return_value=None), \
         patch.object(cards, "render", side_effect=AssertionError("legacy renderer called")):
        assert cards.build_for_pick(_pick("NBA")) is None


def test_non_nba_never_uses_legacy_renderer():
    with patch.object(cards, "ON", True), \
         patch.object(cards, "render", side_effect=AssertionError("legacy renderer called")), \
         patch.object(cards, "player_photo", side_effect=AssertionError("unexpected photo lookup")), \
         patch.object(cards, "team_logo", side_effect=AssertionError("unexpected logo lookup")):
        for sport in ("NFL", "NHL", "MLB", "WNBA"):
            assert cards.build_for_pick(_pick(sport)) is None
