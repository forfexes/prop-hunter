#!/usr/bin/env python3
"""
PROP HUNTER SUPABASE TABLE FIX
==============================

Fix:
Supabase hat keine Tabelle prop_hunter_event_props,
sondern laut Log wahrscheinlich: player_prop_db.

Dieses Script patcht prophunter.py automatisch.
"""

from pathlib import Path

TARGET = Path("prophunter.py")

if not TARGET.exists():
    raise SystemExit("ERROR: prophunter.py not found")

src = TARGET.read_text(encoding="utf-8")

old = """    tables = [
        "prop_hunter_event_props",
        "event_props",
        "prop_event_props",
        "props",
    ]"""

new = """    tables = [
        "player_prop_db",
        "prop_hunter_event_props",
        "event_props",
        "prop_event_props",
        "props",
    ]"""

if old in src:
    src = src.replace(old, new, 1)
elif '"player_prop_db"' not in src and '"prop_hunter_event_props"' in src:
    src = src.replace('"prop_hunter_event_props"', '"player_prop_db",\n        "prop_hunter_event_props"', 1)

repls = {
    '["player", "player_name", "name", "description"]':
    '["player", "player_name", "name", "description", "athlete", "participant", "selection_name"]',

    '["market", "market_name", "prop", "stat", "type"]':
    '["market", "market_name", "prop", "stat", "type", "market_key", "bet_type", "category"]',

    '["line", "point", "handicap", "threshold"]':
    '["line", "point", "points", "handicap", "threshold", "total", "spread"]',

    '["side", "outcome", "over_under", "selection"]':
    '["side", "outcome", "over_under", "selection", "label", "direction"]',

    '["odds", "price", "decimal_odds", "best_odds"]':
    '["odds", "price", "decimal_odds", "best_odds", "book_odds", "value", "odd"]',

    '["prob", "probability", "model_prob", "fair_prob"]':
    '["prob", "probability", "model_prob", "fair_prob", "hit_prob", "projection_prob", "win_prob"]',

    '["edge", "edge_pct", "value_edge"]':
    '["edge", "edge_pct", "value_edge", "ev", "ev_pct", "expected_value"]',

    '["sport", "sport_key", "league"]':
    '["sport", "sport_key", "league", "sport_name"]',

    '["league", "competition"]':
    '["league", "competition", "sport_title"]',

    '["team", "player_team", "home_team"]':
    '["team", "player_team", "home_team", "away_team", "team_name"]',

    '["event_id", "game_id", "match_id", "event", "game"]':
    '["event_id", "game_id", "match_id", "event", "game", "commence_time"]',
}

for a, b in repls.items():
    src = src.replace(a, b)

src = src.replace('"/rest/v1/prop_picks"', '"/rest/v1/prop_hunter_picks"')

TARGET.write_text(src, encoding="utf-8")
print("✅ Supabase table fix applied: player_prop_db added")
