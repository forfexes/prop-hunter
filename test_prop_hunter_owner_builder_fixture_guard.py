"""Offline regression: Owner NBA Builder must never invent a shared matchup."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from prop_hunter_owner_builder_fixture_guard import (
    WrongBuilderFixture, assert_same_game_owner_builder,
)

TEAMS=[("Boston Celtics",object()),("New York Knicks",object())]
VALUES={"date":"23.11.2026","time":"20:00"}


def leg(game="Boston Celtics @ New York Knicks",
        time="2026-11-23T19:00:00Z", event="abc-20"):
    return {"game":game,"commence_time":time,"fixture_id":event}


def test_two_verified_legs_from_same_game_can_use_builder_original():
    assert assert_same_game_owner_builder(
        [leg(),leg(game="New York Knicks vs Boston Celtics")],
        TEAMS,VALUES)


def test_mixed_games_never_display_single_wrong_matchup():
    with pytest.raises(WrongBuilderFixture,match="different game"):
        assert_same_game_owner_builder(
            [leg(),leg("Boston Celtics vs Los Angeles Lakers")],
            TEAMS,VALUES)


def test_no_parent_only_fixture_assumption():
    for details in (
        [],
        [leg(),{"commence_time":"2026-11-23T19:00:00Z"}],
        [leg(),leg(time="")],
        [leg(),leg(time="2026-11-23T20:00:00Z")],
        [leg(),leg(event="different-event-id")],
        [leg(),leg(game="BAD INPUT")],
    ):
        with pytest.raises(WrongBuilderFixture):
            assert_same_game_owner_builder(details,TEAMS,VALUES)


def test_timezone_local_display_must_match_verified_leg():
    with pytest.raises(WrongBuilderFixture,match="conflicting tipoff"):
        assert_same_game_owner_builder(
            [leg(time="2026-11-23T19:00:00Z"),
             leg(time="2026-11-23T21:00:00+02:00")],
            TEAMS,{"date":"23.11.2026","time":"20:01"})


def test_adapter_actually_calls_strict_guard_before_owner_compositor():
    from pathlib import Path
    source=(Path(__file__).resolve().parent /
            "prop_hunter_nba_premium_adapter.py").read_text(encoding="utf-8")
    assert "assert_same_game_owner_builder(" in source
    assert "raise PremiumDataMissing(str(exc)) from exc" in source
