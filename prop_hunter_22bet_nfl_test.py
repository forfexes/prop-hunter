#!/usr/bin/env python3
"""22bet NFL parser: verified-market mapping, direction, fail-closed. No publishing."""
from prop_hunter_22bet_nfl import _subgame_rows, VERIFIED_MARKETS, fetch_22bet_nfl_props, configured

EVENT = {"I": 123, "O1": "Atlanta Falcons", "O2": "Cincinnati Bengals", "S": "2026-11-08T20:30:00"}


def _subval(outcomes):
    return {"Value": {"GE": [{"E": [outcomes]}]}}


def test_verified_passing_yards_mapped():
    # type 8397 = Passing Yards (Joe Burrow 199.5), over + under
    rows = _subgame_rows(_subval([
        {"T": "8397", "PL": {"N": "Joe Burrow over", "I": 1}, "P": 199.5, "C": 1.9},
        {"T": "8397", "PL": {"N": "Joe Burrow under", "I": 1}, "P": 199.5, "C": 1.9},
    ]), EVENT)
    assert len(rows) == 2, rows
    assert all(r["market_key"] == "passing_yards" for r in rows)
    assert {r["direction"] for r in rows} == {"over", "under"}
    assert all(r["line"] == 199.5 and r["player_name"].startswith("Joe Burrow") for r in rows)
    assert all(r["bookmaker"] == "22bet" and r["odds_observed"] is True for r in rows)


def test_unmapped_type_dropped():
    # type 9999 is not in VERIFIED_MARKETS -> must be dropped, never guessed
    rows = _subgame_rows(_subval([
        {"T": "9999", "PL": {"N": "Some Player over", "I": 2}, "P": 1.5, "C": 2.0},
    ]), EVENT)
    assert rows == [], rows


def test_ambiguous_direction_skipped():
    # no over/under token and unknown type -> direction empty -> skip
    rows = _subgame_rows(_subval([
        {"T": "6188", "PL": {"N": "Bijan Robinson", "I": 3}, "P": 0.5, "C": 1.8},
    ]), EVENT)
    assert rows == [], rows


def test_line_band_guard():
    # passing_yards with an impossible line (0.5) is dropped by the band guard
    rows = _subgame_rows(_subval([
        {"T": "8397", "PL": {"N": "Joe Burrow over", "I": 1}, "P": 0.5, "C": 1.9},
    ]), EVENT)
    assert rows == [], rows


def test_touchdowns_mapped():
    rows = _subgame_rows(_subval([
        {"T": "6188", "PL": {"N": "Bijan Robinson over", "I": 4}, "P": 0.5, "C": 1.8},
        {"T": "6188", "PL": {"N": "Bijan Robinson under", "I": 4}, "P": 0.5, "C": 2.0},
    ]), EVENT)
    assert len(rows) == 2 and all(r["market_key"] == "touchdowns" for r in rows), rows


def test_fetch_fail_closed_when_disabled():
    # default off -> no network, empty
    assert fetch_22bet_nfl_props() == []


if __name__ == "__main__":
    test_verified_passing_yards_mapped()
    test_unmapped_type_dropped()
    test_ambiguous_direction_skipped()
    test_line_band_guard()
    test_touchdowns_mapped()
    test_fetch_fail_closed_when_disabled()
    print("22bet NFL verified-mapping, fail-closed and direction tests passed")
