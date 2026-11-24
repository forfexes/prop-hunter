"""Exact-image-source identity tests: no network, no asset redistribution."""
import unittest

from prop_hunter_hockey_source_candidates import (
    CANDIDATES, official_source, roster_source,
)
from prop_hunter_asset_identity import normalized_team, resolve_provider


class SwissSourceIdentity(unittest.TestCase):
    def test_all_ten_original_swiss_nl_names_have_official_club_leads(self):
        expected={
            "Leonardo Genoni":"EV Zug",
            "Julien Sprunger":"Fribourg-Gottéron",
            "Philipp Kurashev":"Lausanne HC",
            "Kevin Fey":"HC Ajoie",
            "Luca Fazzini":"HC Lugano",
            "Simon Hrubec":"ZSC Lions",
            "Markus Granlund":"Genève-Servette HC",
            "Rasmus Kupari":"HC Lugano",
            "Jesper Frödén":"ZSC Lions",
            "Miro Aaltonen":"SC Bern",
        }
        self.assertEqual({c.player:c.team for c in CANDIDATES},expected)
        self.assertEqual(len({c.url for c in CANDIDATES}),10)
        for name, team in expected.items():
            with self.subTest(name=name):
                source=official_source(name,team,"SWISS_NL")
                self.assertIsNotNone(source)
                self.assertTrue(source.url.startswith("https://"))
                self.assertFalse(source.import_approved)
                self.assertEqual(source.image_license,"unverified")
                self.assertIsNone(official_source(name,team,"NHL"))

    def test_surname_or_wrong_roster_never_gets_wrong_hockey_player(self):
        self.assertIsNone(roster_source("Genoni", {"EV Zug"}, {"SWISS_NL"}))
        self.assertIsNone(roster_source("Leonardo Genoni", {"ZSC Lions"}, {"SWISS_NL"}))
        self.assertIsNone(roster_source("Leonardo Genoni", {"EV Zug","SC Bern"}, {"SWISS_NL"}))
        self.assertIsNone(roster_source("Leonardo Genoni", {"EV Zug"}, {"SWISS_NL","SHL"}))
        self.assertIsNone(roster_source("Jhonas Enroth", {"OHK"}, {"SHL"}))
        self.assertIsNone(roster_source("Joshua Roy", {"TUC"}, {"AHL"}))
        self.assertIsNotNone(roster_source("Leonardo Genoni", {"EV Zug"}, {"SWISS_NL"}))

    def test_all_nba_franchise_aliases_are_blocked_in_euroleague(self):
        for name in ("LA Clippers","UTA","Utah Jazz","BOS","Boston Celtics","PHO Suns"):
            with self.subTest(team=name):
                actual,reason=normalized_team(name,"EUROLEAGUE")
                self.assertIsNone(actual)
                self.assertIn("NBA",reason)
        actual,reason=normalized_team("FC Bayern München","EUROLEAGUE")
        self.assertEqual(actual,"FC Bayern München")
        self.assertEqual(reason,"exact_source_name")

    def test_real_swiss_competition_stays_separate_from_nhl(self):
        for league in ("SWISS_NL","SHL","AHL"):
            provider,reason,code=resolve_provider("ICE_HOCKEY",{league})
            self.assertIsNone(provider)
            self.assertIn("not_configured",reason)
            self.assertEqual(code,league)


if __name__ == "__main__":
    unittest.main()
