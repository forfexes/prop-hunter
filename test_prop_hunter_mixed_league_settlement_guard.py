"""Fail-closed offline checks for mixed-league card publication AND settlement.

No live data, Telegram, Supabase, photos or network calls are permitted.
"""
from types import SimpleNamespace
from unittest.mock import patch

from prop_hunter_image_cards import build_for_pick, settled_image


def test_mismatched_legs_cannot_use_nba_original():
    for bad_sport in ("NFL", "WNBA", "NHL", "basketball", "UNKNOWN"):
        details = [
            {"sport": "NBA", "player": "NBA TEST PLAYER", "odds": 1.80},
            {"sport": bad_sport, "player": "OTHER TEST PLAYER", "odds": 1.90},
        ]
        item = SimpleNamespace(type="builder", source_sport="NBA",
                               sport="NBA", game="Home vs Away",
                               leg_details=details, features={})
        snapshot = {"type": "builder", "source_sport": "NBA",
                    "sport": "NBA", "game": "Home vs Away",
                    "leg_details": details, "features": {}}
        with patch("prop_hunter_image_cards.player_photo",
                   side_effect=AssertionError("Unexpected photo request")), \
             patch("prop_hunter_image_cards.team_logo",
                   side_effect=AssertionError("Unexpected crest request")), \
             patch("prop_hunter_image_cards.requests.get",
                   side_effect=AssertionError("Unexpected network request")):
            assert build_for_pick(item) is None, bad_sport
            assert settled_image(snapshot, "🏁 Auswertung: 1✅ 1❌") is None, bad_sport


if __name__ == "__main__":
    test_mismatched_legs_cannot_use_nba_original()
    print("MIXED-LEAGUE ORIGINAL IMAGE AND SETTLEMENT BLOCK: PASS")
