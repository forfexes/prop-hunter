"""Offline safety contract for NFL/NHL card assets (not production cards).

Do not misrepresent the shared visual hierarchy as approved league-specific
logos, blank masters, athlete photos, or bookmaker data.
"""
from pathlib import Path
from prop_hunter_original_template_registry import (
    FAMILIES, SPORTS, ORIGINAL_REFERENCE_NAMES, available_template,
    template_location, league_required_templates, sport_family,
    league_is_ready,
)

assert len(FAMILIES) == 4
assert set(SPORTS) == {
    "NBA", "NFL", "NHL", "MLB", "WNBA", "NCAAF", "NCAAB", "EUROLEAGUE"
}
for league in SPORTS:
    expected = f"{league.lower()}"
    assert sport_family(league) == expected
    targets = league_required_templates(league)
    assert len(targets) == 4
    assert [target.name for target in targets] == [f"{family}.webp" for family in FAMILIES]
    assert all(target.parent.name == expected for target in targets)
    assert league_is_ready(league) == all(target.is_file() for target in targets)

for family in FAMILIES:
    nba_path = template_location("NBA", family)
    assert template_location("NFL", family) != nba_path, "NFL cannot show NBA artwork"
    assert template_location("NHL", family) != nba_path, "NHL cannot show NBA artwork"
    assert template_location("NFL", family) != template_location("NHL", family)
    assert template_location("WNBA", family) != nba_path
    assert template_location("MLB", family) != nba_path

for key, original_name in ORIGINAL_REFERENCE_NAMES.items():
    reference = Path("card_templates/originals") / original_name
    assert reference.is_file(), reference
    assert reference.suffix == ".jpg"

for invalid in ("", "Unknown League", "nba/nfl", "../nba", "NF L"):
    try:
        league_required_templates(invalid)
    except ValueError:
        pass
    else:
        raise AssertionError(f"Unsafe invalid league accepted: {invalid!r}")

print("NFL NHL ORIGINAL-STYLE SLOTS ISOLATED: 4 EACH")
print("No unapproved source is enabled for Telegram production")
print("Current NFL slots:",
      ", ".join("available" if p.is_file() else "missing" for p in league_required_templates("NFL")))
print("Current NHL slots:",
      ", ".join("available" if p.is_file() else "missing" for p in league_required_templates("NHL")))
