"""The approved original one-player Ladder must always show all form windows.

Missing gamelog records are UNKNOWN (—), not invented hit counts.
"""
from prop_hunter_owner_clean_ladder import _observed_form_windows

assert _observed_form_windows(
    "L5 5/5 L10 10/10 L15 13/15"
) == "L5 5/5 · L10 10/10 · L15 13/15"
assert _observed_form_windows(
    "L15 13/15"
) == "L5 — · L10 — · L15 13/15"
assert _observed_form_windows(None) == "L5 — · L10 — · L15 —"
assert _observed_form_windows(
    "L5 6/5 L10 11/10 L15 16/15"
) == "L5 — · L10 — · L15 —"
assert _observed_form_windows(
    "L5 0/0 L10 2/10 L15 11/15"
) == "L5 — · L10 2/10 · L15 11/15"
print("ONE_PLAYER_OWNER_LADDER_L5_L10_L15_VISIBLE_NO_FAKE_STATS_PASS")
