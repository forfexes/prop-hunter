#!/usr/bin/env python3
"""Offline regression test for sportsbook threshold/market mapping.

Covers the 25.09.2026 failure mode where FanDuel threshold props arrived with a
placeholder handicap=0 and "to hit a triple" was then matched to generic Hits.
"""
from prop_hunter_quote_guard import canonical_market, probability_sane, sanitize_row

def check(value, message):
    if not value:
        raise AssertionError(message)

def _row(player, market, line, odds):
    return {
        "source": "fanduel_direct",
        "bookmaker": "fanduel",
        "sport": "MLB",
        "league": "MLB",
        "source_event_id": "fixture",
        "player_name": player,
        "market": market.lower().replace(" ", "_"),
        "market_key": market.lower().replace(" ", "_"),
        "direction": "over",
        "line": line,
        "odds_decimal": odds,
        "selection": market,
        "raw": {"market_name": market},
    }

def main():
    cases = [
        (_row("Javier Sanoja", "To Record 4+ Hits", 0, 71.0), "hits", 3.5),
        (_row("Miguel Vargas", "To Hit A Triple", 0, 36.0), "triples", 0.5),
        (_row("Otto Lopez", "To Hit A Double", 0, 4.2), "doubles", 0.5),
        (_row("Jo Adell", "To Hit A Single", 0, 2.05), "singles", 0.5),
        (_row("Mike Trout", "To Hit 2+ Home Runs", 0, 51.0), "home_runs", 1.5),
    ]
    for raw, expected_market, expected_line in cases:
        fixed = sanitize_row(raw)
        check(fixed is not None, f"row rejected unexpectedly: {raw}")
        check(fixed["market_key"] == expected_market, f"market {fixed['market_key']} != {expected_market}")
        check(abs(float(fixed["line"]) - expected_line) < 1e-9, f"line {fixed['line']} != {expected_line}")

    check(canonical_market("to_hit_a_triple") == "triples", "triple mapped to generic hits")
    check(canonical_market("to_hit_a_double") == "doubles", "double mapped to generic hits")
    check(canonical_market("to_hit_a_single") == "singles", "single mapped to generic hits")
    check(not probability_sane(.91, 71.0), "91% @71 absurd probability accepted")
    future = sanitize_row({
        "source":"draftkings_direct","bookmaker":"draftkings","sport":"NHL",
        "player_name":"ANA Ducks October Standings","market":"points","direction":"under",
        "line":15.5,"odds_decimal":1.83,"home_team":"Anaheim Ducks","away_team":"LA Kings",
        "selection":"Under 15.5","raw":{"market_name":"October Standings Points"}
    })
    check(future is None, "standings/futures row reached card-eligible pool")
    check(not probability_sane(.92, 36.0), "92% @36 absurd probability accepted")
    check(probability_sane(.60, 1.90), "reasonable probability rejected")

    print("MARKET REGRESSION OK: threshold lines + single/double/triple mapping + probability guard")

if __name__ == "__main__":
    main()
