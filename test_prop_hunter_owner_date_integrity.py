"""Offline regression for owner-original NBA cards: never guess a match year."""
import unittest
import prop_hunter_original_compositor as original


class OwnerDateIntegrityTests(unittest.TestCase):
    def test_verified_year_and_clock_are_preserved(self):
        date, clock, venue, city = original._panel_fields(
            "HOME vs AWAY · So 22.11.2026 · 20:15")
        self.assertEqual(date, "So, 22. Nov 2026")
        self.assertEqual(clock, "20:15 Uhr")
        self.assertEqual((venue, city), ("", ""))

    def test_historical_fixture_never_uses_current_year(self):
        date, clock, _, _ = original._panel_fields(
            "HOME vs AWAY · Sa 15.06.2024 · 19:40")
        self.assertEqual(date, "Sa, 15. Jun 2024")
        self.assertEqual(clock, "19:40 Uhr")

    def test_legacy_caption_without_year_does_not_invent_one(self):
        date, clock, _, _ = original._panel_fields(
            "HOME vs AWAY · So 22.11. · 20:15")
        self.assertEqual(date, "So, 22. Nov")
        self.assertEqual(clock, "20:15 Uhr")

    def test_status_panel_keeps_full_verified_kickoff(self):
        source = "HOME vs AWAY · So 22.11.2026 · 20:15"
        self.assertEqual(original._verified_kickoff_label(source),
                         "So 22.11.2026 · 20:15")

    def test_bad_month_is_rejected_not_displayed(self):
        with self.assertRaisesRegex(ValueError, "Invalid verified NBA date"):
            original._panel_fields("HOME vs AWAY · So 22.19.2026 · 20:15")


if __name__ == "__main__":
    unittest.main()
