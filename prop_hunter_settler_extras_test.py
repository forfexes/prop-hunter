#!/usr/bin/env python3
"""Protect touchdown settlement against missing official stat fields."""
from prop_hunter_settler_extras import extra_stat_value

def test_missing_touchdown_components():
    assert extra_stat_value({}, "touchdowns") is None
    assert extra_stat_value({"receiving_touchdowns": 1}, "touchdowns") is None
    assert extra_stat_value({"rushing_touchdowns": 1}, "touchdowns") is None

def test_complete_touchdown_components():
    assert extra_stat_value({"receiving_touchdowns": 0, "rushing_touchdowns": 0}, "touchdowns") == 0
    assert extra_stat_value({"receiving_touchdowns": 1, "rushing_touchdowns": 2}, "touchdowns") == 3

if __name__ == "__main__":
    test_missing_touchdown_components()
    test_complete_touchdown_components()
    print("Touchdown settlement missing-data guard passed")
