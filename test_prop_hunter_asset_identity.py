"""No-network exact identity and league tests for 2026 PROP HUNTER assets."""
import unittest
from unittest.mock import patch

from prop_hunter_asset_identity import normalized_team, resolve_provider
import prop_hunter_image_cards as cards


class LeagueIdentity(unittest.TestCase):
    def test_swiss_nl_is_not_nhl(self):
        names = ("Leonardo Genoni", "Julien Sprunger", "Philipp Kurashev",
                 "Kevin Fey", "Luca Fazzini", "Simon Hrubec", "Markus Granlund",
                 "Rasmus Kupari", "Jesper Frödén", "Miro Aaltonen")
        for name in names:
            with self.subTest(name=name):
                league, reason, code = resolve_provider("ICE_HOCKEY", {"SWISS_NL"})
                self.assertIsNone(league)
                self.assertEqual(code, "SWISS_NL")
                self.assertEqual(reason, "league_provider_not_configured:SWISS_NL")
                self.assertIsNone(cards.league_of("SWISS_NL"))
                self.assertIsNone(cards.league_of("ICE_HOCKEY"))

    def test_shl_and_ahl_are_not_nhl(self):
        for league_name in ("SHL", "AHL"):
            with self.subTest(league=league_name):
                result, why, code = resolve_provider("ICE_HOCKEY", {league_name})
                self.assertIsNone(result)
                self.assertEqual(why, "league_provider_not_configured:" + league_name)
                self.assertEqual(code, league_name)
        self.assertEqual(resolve_provider("ICE_HOCKEY", {"NHL"})[0],
                         ("hockey", "nhl"))

    def test_source_competition_prevents_wrong_provider(self):
        self.assertEqual(resolve_provider("NBA", {"EUROLEAGUE"})[0], None)
        self.assertIn("league_sport_conflict",
                      resolve_provider("NBA", {"EUROLEAGUE"})[1])
        self.assertIn("league_multiple",
                      resolve_provider("ICE_HOCKEY", {"SHL", "SWISS_NL"})[1])
        self.assertEqual(resolve_provider("BASKETBALL", {"NBA"})[0],
                         ("basketball", "nba"))

    def test_safe_exact_team_aliases(self):
        samples = [
            ("LAK", "NHL", "Los Angeles Kings"),
            ("SJS", "NHL", "San Jose Sharks"),
            ("TBL", "NHL", "Tampa Bay Lightning"),
            ("VGS Golden Knights", "NHL", "Vegas Golden Knights"),
            ("NY Jets", "NFL", "New York Jets"),
            ("CWS", "MLB", "Chicago White Sox"),
            ("UTA", "NBA", "Utah Jazz"),
        ]
        for original, league, expected in samples:
            with self.subTest(team=original):
                actual, why = normalized_team(original, league)
                self.assertEqual(actual, expected)
                self.assertEqual(why, "verified_alias")

    def test_never_borrow_nba_crest_into_euroleague(self):
        for team in ("Utah Jazz", "Boston Celtics", "Sacramento Kings",
                     "Phoenix Suns", "Los Angeles Lakers"):
            with self.subTest(team=team):
                matched, status = normalized_team(team, "EUROLEAGUE")
                self.assertIsNone(matched)
                self.assertTrue(status.startswith("team_league_conflict:"))
        for team in ("Adelaide 36ers", "Illawarra Hawks"):
            self.assertIsNone(normalized_team(team, "EUROLEAGUE")[0])
        self.assertEqual(normalized_team("Zalgiris Kaunas", "EUROLEAGUE"),
                         ("Zalgiris Kaunas", "exact_source_name"))

    def test_team_logo_alias_uses_same_sport_only(self):
        cards._CACHE.clear()
        fake_teams = {"sports":[{"leagues":[{"teams":[
            {"team":{"displayName":"Los Angeles Kings","shortDisplayName":"LA Kings",
                     "name":"Kings","abbreviation":"LA","logos":[{"href":"https://example.test/kings.png"}]}}
        ]}]}]}
        with patch.object(cards, "_get_json", return_value=fake_teams) as lookup, \
             patch.object(cards, "_get_image", return_value="EXPECTED-KINGS-LOGO") as getimg:
            self.assertEqual(cards.team_logo("LAK", ("hockey","nhl")), "EXPECTED-KINGS-LOGO")
            self.assertEqual(getimg.call_args.args[0], "https://example.test/kings.png")
            self.assertEqual(lookup.call_count, 1)
        cards._CACHE.clear()

    def test_mislabeled_euroleague_team_never_looks_up_logo(self):
        with patch.object(cards, "_get_json", side_effect=AssertionError("wrong ESPN lookup")), \
             patch.object(cards, "_get_image", side_effect=AssertionError("wrong logo fetch")):
            self.assertIsNone(cards.team_logo("Utah Jazz", ("basketball","euroleague")))


if __name__ == "__main__":
    unittest.main()
