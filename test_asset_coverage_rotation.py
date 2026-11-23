"""Daily image QA scans every name over time without repeating one fixed sample."""
import unittest
from asset_coverage_audit import select_batch


class CoverageRotation(unittest.TestCase):
    def test_fixed_priority_and_daily_progress(self):
        items = list(range(55))
        first, meta = select_batch(items, 10, rotate=True, anchor=2, ordinal=0)
        second, meta2 = select_batch(items, 10, rotate=True, anchor=2, ordinal=1)
        self.assertEqual(first[:2], [0, 1])
        self.assertEqual(second[:2], [0, 1])
        self.assertEqual(first[2:], list(range(2, 10)))
        self.assertEqual(second[2:], list(range(10, 18)))
        self.assertEqual(meta["mode"], "daily_rotation")
        self.assertEqual(meta["slices"], meta2["slices"])

    def test_all_names_eventually_scanned(self):
        items = list(range(55))
        covered = set()
        for day in range(12):
            selected, meta = select_batch(items, 10, rotate=True, anchor=2, ordinal=day)
            self.assertEqual(len(selected), len(set(selected)))
            covered.update(selected)
        self.assertEqual(covered, set(items))

    def test_priority_mode_backwards_compatible(self):
        selected, meta = select_batch(list(range(12)), 5)
        self.assertEqual(selected, [0, 1, 2, 3, 4])
        self.assertEqual(meta["mode"], "priority")

    def test_empty_and_small_rosters(self):
        self.assertEqual(select_batch([], 10, rotate=True)[0], [])
        self.assertEqual(select_batch([1, 2, 3], 10, rotate=True)[0], [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
