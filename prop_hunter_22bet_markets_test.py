#!/usr/bin/env python3
"""Tests for the verified 22bet multi-sport parser."""
from prop_hunter_22bet_markets import parse_players_stats, VERIFIED_MARKETS

EV = {"I": 12345, "O1": "Baltimore Ravens", "O2": "Houston Texans", "S": "1731790800"}


def _sub(outcomes):
    return {"Value": {"GE": [{"E": [outcomes]}]}}


def test_nfl_verified_markets():
    rows = parse_players_stats(_sub([
        {"T": 8395, "P": 5.5, "C": 1.909, "PL": {"N": "Derrick Henry", "I": 1, "T": 1}},
        {"T": 8396, "P": 5.5, "C": 1.833, "PL": {"N": "Derrick Henry", "I": 1, "T": 1}},
        {"T": 8397, "P": 193.5, "C": 1.87, "PL": {"N": "Justin Herbert", "I": 2, "T": 2}},
        {"T": 8393, "P": 3.5, "C": 1.95, "PL": {"N": "Zay Flowers", "I": 3, "T": 1}},
        {"T": 6188, "P": 0.5, "C": 6.5, "PL": {"N": "Derrick Henry", "I": 1, "T": 1}},
    ]), EV, "NFL")
    by = {(r["player_name"], r["market"], r["direction"]): r for r in rows}
    # 8393-8396 have contradictory/unresolved meanings: deliberately NOT mapped
    # (fail-closed) until an operator verifies them from a probe.
    assert ("Derrick Henry", "rushing_yards", "over") not in by
    assert ("Derrick Henry", "rushing_yards", "under") not in by
    assert ("Zay Flowers", "receptions", "over") not in by
    assert ("Justin Herbert", "passing_yards", "over") in by
    assert ("Derrick Henry", "anytime_td", "yes") in by
    assert by[("Derrick Henry", "anytime_td", "yes")]["line"] == 0.5
    print("NFL verified markets OK")


def test_unverified_type_dropped():
    rows = parse_players_stats(_sub([
        {"T": 99999, "P": 1.5, "C": 2.0, "PL": {"N": "Ghost Market", "I": 9}},
        {"T": 8397, "P": 193.5, "C": 1.9, "PL": {"N": "Real QB", "I": 8, "T": 1}},
    ]), EV, "NFL")
    assert len(rows) == 1 and rows[0]["player_name"] == "Real QB", "unverified type must be dropped"
    print("unverified type dropped OK")


def test_nba_mlb_fail_closed():
    # No verified markets yet -> no rows, even with plausible-looking data.
    for sport in ("NBA", "MLB", "WNBA"):
        rows = parse_players_stats(_sub([
            {"T": 8395, "P": 25.5, "C": 1.9, "PL": {"N": "Some Player", "I": 1}},
        ]), EV, sport)
        assert rows == [], f"{sport} must be fail-closed until verified"
    print("NBA/MLB/WNBA fail-closed OK")


def test_line_band_rejects_absurd():
    rows = parse_players_stats(_sub([
        {"T": 8397, "P": 9999.5, "C": 1.9, "PL": {"N": "Glitch QB", "I": 1, "T": 2}},
        {"T": 8397, "P": 224.5, "C": 1.9, "PL": {"N": "Good QB", "I": 2, "T": 2}},
    ]), EV, "NFL")
    assert len(rows) == 1 and rows[0]["player_name"] == "Good QB", "absurd line must be rejected"
    print("line band rejects absurd OK")


def test_odds_and_player_guards():
    rows = parse_players_stats(_sub([
        {"T": 8395, "P": 4.5, "C": 99.0, "PL": {"N": "Too High Odds", "I": 1, "T": 1}},
        {"T": 8395, "P": 4.5, "C": 1.9, "PL": None},  # no player
        {"T": 8395, "P": 4.5, "C": 1.9, "PL": {"N": "", "I": 1}},  # empty name
    ]), EV, "NFL")
    assert rows == [], "odds>51, missing/empty players must be dropped"
    print("odds and player guards OK")


if __name__ == "__main__":
    test_nfl_verified_markets()
    test_unverified_type_dropped()
    test_nba_mlb_fail_closed()
    test_line_band_rejects_absurd()
    test_odds_and_player_guards()
    print("ALL 22bet market tests passed")
