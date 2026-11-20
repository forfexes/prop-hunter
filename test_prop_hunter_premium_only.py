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


def test_nba_uses_premium_adapter_and_never_legacy():
    """Successful NBA cards must come from the premium adapter only."""
    fake_png = bytes([137, 80, 78, 71, 13, 10, 26, 10]) + b"PREMIUM"
    with patch.object(cards, "ON", True), \
         patch.object(cards, "player_photo", return_value=None), \
         patch.object(cards, "team_logo", return_value=None), \
         patch("prop_hunter_nba_premium_adapter.render_nba_pick", return_value=fake_png) as premium, \
         patch.object(cards, "render", side_effect=AssertionError("legacy renderer called")):
        assert cards.build_for_pick(_pick("NBA")) == fake_png
        premium.assert_called_once()


def test_ambiguous_basketball_never_becomes_nba():
    assert cards.league_of("basketball") is None
    assert cards.league_of("basketball_wnba") == ("basketball", "wnba")
    assert cards.league_of("basketball_nba") == ("basketball", "nba")
    with patch.object(cards, "ON", True), \\
         patch.object(cards, "player_photo", side_effect=AssertionError("unexpected network lookup")), \\
         patch.object(cards, "team_logo", side_effect=AssertionError("unexpected network lookup")):
        assert cards.build_for_pick(_pick("basketball")) is None
