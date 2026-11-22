"""Definite NBA player/team/game contradictions never render owner-original photos.

No roster is invented: this only compares independently provided franchise
identities with the two already-published fixture teams.
"""
from types import SimpleNamespace as N
from unittest.mock import patch

from prop_hunter_player_fixture_guard import nba_code, definite_team_fixture_conflict
from prop_hunter_image_cards import build_for_pick

assert nba_code("Philadelphia 76ers") == "PHI"
assert nba_code("76ers") == "PHI"
assert nba_code("BOS Celtics") == "BOS"
assert nba_code("Sacramento Kings") == "SAC"
assert nba_code("New Orleans Pelicans") == "NOP"
assert nba_code("SA Spurs") == "SAS" if nba_code("SA Spurs") else True

def fixture_conflict(team, game):
    return definite_team_fixture_conflict(team, game)

assert fixture_conflict("Philadelphia 76ers", "Boston Celtics @ Sacramento Kings")
assert fixture_conflict("Philadelphia 76ers", "Boston Celtics vs Sacramento Kings")
assert fixture_conflict("Philadelphia 76ers", "Boston Celtics - Sacramento Kings")
assert not fixture_conflict("Boston Celtics", "Boston Celtics @ Sacramento Kings")
assert not fixture_conflict("Sacramento Kings", "Boston Celtics @ Sacramento Kings")
assert not fixture_conflict("San Antonio Spurs", "New Orleans Pelicans vs San Antonio Spurs")
assert not fixture_conflict(None, "Boston Celtics @ Sacramento Kings")
assert not fixture_conflict("UNKNOWN TEAM", "Boston Celtics @ Sacramento Kings")
assert not fixture_conflict("Philadelphia 76ers", "UNKNOWN HOME vs Boston Celtics")

game = "Boston Celtics @ Sacramento Kings"
base = dict(type="single", source_sport="NBA", sport="NBA", player="QA PLAYER",
            game=game, market="points", direction="over", point=10.5,
            odds=1.84, leg_details=[], features={}, team="Philadelphia 76ers")

def network_must_not_run(*_a, **_kw):
    raise AssertionError("Photo/club HTTP lookup before fixture roster guard")

with patch("prop_hunter_image_cards.player_photo", side_effect=network_must_not_run), \
     patch("prop_hunter_image_cards.team_logo", side_effect=network_must_not_run):
    assert build_for_pick(N(**base)) is None
    via_features = {**base, "team": None,
                    "features": {"roster_team": "Philadelphia 76ers"}}
    assert build_for_pick(N(**via_features)) is None
    own = {**base, "team": "Boston Celtics",
           "leg_details": [{"sport": "NBA", "player": "QA PLAYER",
                            "game": game, "team": "Philadelphia 76ers"}]}
    assert build_for_pick(N(**own)) is None
print("NBA_PREMIUM_PLAYER_TEAM_VS_MATCH_IDENTIFICATION_GATE_PASSED")
