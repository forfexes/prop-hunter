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
            ("nba", "LA Lakers", "Los Angeles Lakers", "LAL"),
            ("nhl", "NY Rangers", "New York Rangers", "NYR"),
            ("nhl", "WAS Capitals", "Washington Capitals", "WSH"),
            ("nfl", "WAS Commanders", "Washington Commanders", "WSH"),
            ("nfl", "NY Giants", "New York Giants", "NYG"),
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


    def test_full_college_team_list_and_rank_prefix(self):
        logo = object()
        feed = {"sports":[{"leagues":[{"teams":[{"team":{
            "displayName":"Florida Gators", "shortDisplayName":"Florida",
            "name":"Gators", "abbreviation":"FLA",
            "nickname":"Gators", "logos":[{"href":"https://a.espncdn.com/florida.png"}]
        }}]}]}]}
        with patch.object(cards,"_CACHE",{}), \
             patch.object(cards,"_get_json",return_value=feed) as get, \
             patch.object(cards,"_get_image",return_value=logo):
            self.assertIs(cards.team_logo("(23) Florida", cards.LEAGUES["ncaaf"]),logo)
            self.assertEqual(get.call_args.args[1], {"limit": 500})


if __name__ == "__main__":
    unittest.main()
