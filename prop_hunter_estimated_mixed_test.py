#!/usr/bin/env python3
"""Estimated team+player mixed builder: flagged, P/L-invalidated, fail-closed."""
import os
os.environ["PH_ESTIMATED_SAME_GAME_BUILDERS"] = "1"

from prop_hunter_estimated_mixed import build_estimated_mixed
from prop_hunter_combo_prices import publishable_extra, unpriced_sgp


class Pick:
    def __init__(self, **k):
        for a, v in k.items():
            setattr(self, a, v)


def _team(odds, mk="game_total_points", line=220.5):
    return {"player": "GAME", "player_name": "GAME", "market": "Game Total Points",
            "market_key": mk, "direction": "over", "point": line, "line": line,
            "odds": odds, "sport": "NBA", "game": "LAL @ BOS",
            "features": {"odds_observed": True, "bookmaker": "draftkings"},
            "raw": {"event_market": True}}


def _player(name, market, odds, line):
    return {"player": name, "market": market, "market_key": market.lower(),
            "direction": "over", "point": line, "odds": odds, "sport": "NBA",
            "game": "LAL @ BOS", "features": {"odds_observed": True, "bookmaker": "draftkings"}}


def test_builds_team_plus_players():
    props = [
        _team(1.9),
        _player("LeBron James", "points", 1.8, 24.5),
        _player("Jayson Tatum", "assists", 2.0, 5.5),
        _player("Anthony Davis", "rebounds", 1.95, 10.5),
    ]
    tickets = build_estimated_mixed(props, Pick)
    assert len(tickets) == 1, tickets
    t = tickets[0]
    # team leg + up to 3 players, product price
    assert t.type == "betbuilder" and t.features["mixed_team_player"] is True
    assert t.features["builder_odds_estimated_from_legs"] is True
    assert len(t.leg_details) >= 2
    # one GAME leg present
    assert any(str(l["player"]).upper() == "GAME" for l in t.leg_details)


def test_card_shows_as_estimated_and_pl_invalidated():
    props = [_team(1.9), _player("LeBron James", "points", 1.8, 24.5)]
    t = build_estimated_mixed(props, Pick)[0]
    # publishable because flagged estimated (opt-in on)
    assert publishable_extra(t) is True
    # but invalidated in realised P/L
    assert unpriced_sgp(t) is True


def test_fail_closed_when_disabled():
    os.environ["PH_ESTIMATED_SAME_GAME_BUILDERS"] = "0"
    props = [_team(1.9), _player("LeBron James", "points", 1.8, 24.5)]
    assert build_estimated_mixed(props, Pick) == []
    os.environ["PH_ESTIMATED_SAME_GAME_BUILDERS"] = "1"


def test_no_team_leg_no_ticket():
    props = [_player("LeBron James", "points", 1.8, 24.5), _player("Jayson Tatum", "assists", 2.0, 5.5)]
    assert build_estimated_mixed(props, Pick) == []


if __name__ == "__main__":
    test_builds_team_plus_players()
    test_card_shows_as_estimated_and_pl_invalidated()
    test_fail_closed_when_disabled()
    test_no_team_leg_no_ticket()
    print("estimated team+player mixed builder tests passed")
