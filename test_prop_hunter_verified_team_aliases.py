"""Offline identity tests for approved provider team-name aliases. No network."""
import unittest
from unittest.mock import patch
import prop_hunter_image_cards as cards


class VerifiedTeamAliases(unittest.TestCase):
    def test_correct_league_and_exact_team_match(self):
        cases = [
            ("nba", "Los Angeles Clippers", "LA Clippers", "LAC"),
            ("nba", "WAS Wizards", "Washington Wizards", "WSH"),
            ("nba", "UTA Jazz", "Utah Jazz", "UTAH"),
            ("nhl", "UTA Mammoth", "Utah Mammoth", "UTA"),
            ("nfl", "LA Chargers", "Los Angeles Chargers", "LAC"),
        ]
        for sport, feed_name, official, abbr in cases:
            with self.subTest(feed_name=feed_name):
                fake_photo = object()
                source = {"sports":[{"leagues":[{"teams":[{"team":{
                    "displayName": official,
                    "abbreviation": abbr,
                    "nickname": official.split()[-1],
                    "logos": [{"href":"https://a.espncdn.com/verified.png"}]
                }}]}]}]}
                with patch.object(cards, "_CACHE", {}), \
                     patch.object(cards, "_get_json", return_value=source), \
                     patch.object(cards, "_get_image", return_value=fake_photo):
                    self.assertIs(cards.team_logo(feed_name, cards.LEAGUES[sport]), fake_photo)
                    self.assertIsNone(cards.team_logo("Other Team", cards.LEAGUES[sport]))


if __name__ == "__main__":
    unittest.main()
