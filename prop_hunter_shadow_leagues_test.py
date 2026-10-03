#!/usr/bin/env python3
from pathlib import Path

from prop_hunter_shadow_leagues import SHADOW_LEAGUES, _shadow_row

expected = {"SWISS_NL", "EUROCUP", "AHL", "SHL", "NBA_G_LEAGUE", "CFL"}
assert expected <= set(SHADOW_LEAGUES)

sample = {
    "source": "sportsgameodds",
    "bookmaker": "testbook",
    "sport": "AHL",
    "league": "AHL",
    "source_event_id": "evt-1",
    "player_name": "Test Player",
    "market": "shots_on_goal",
    "market_key": "shots_on_goal",
    "direction": "over",
    "line": 2.5,
    "odds_decimal": 1.91,
    "raw": {"score": 4, "scoring_supported": True},
}
row = _shadow_row(sample, "AHL", "sportsgameodds")
assert row is not None
assert row["card_eligible"] is False
assert row["settlement_supported"] is False
assert row["risk_class"] == "shadow"
assert row["snapshot_id"]
assert row["raw"]["shadow_league"] is True

sgo = Path("prop_hunter_sgo.py").read_text(encoding="utf-8")
for token in ("icehockey_ahl", "icehockey_shl", "basketball_g_league", "americanfootball_cfl"):
    assert token in sgo, token
for token in ('"score": odd.get("score")', '"scoring_supported": odd.get("scoringSupported")', '"event_finalized"'):
    assert token in sgo, token

print("SHADOW LEAGUES TEST PASSED")
