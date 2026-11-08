#!/usr/bin/env python3
"""Estimated team+player same-game builders (opt-in, clearly flagged).

Builds the JK-style mixed ticket the user asked for, e.g.
    Team X over 220.5 points
    Player 1 over 25 points
    Player 2 over 7 assists
    Player 3 over 10 rebounds
from a single game (same team or mixed), combining OBSERVED single legs.

The total price is the PRODUCT of the single legs. For a same-game ticket the
legs are correlated, so that product is only an ESTIMATE — the real SGP quote
at the book will differ. Every ticket is therefore flagged
`builder_odds_estimated_from_legs=True`, which makes the card show
"finale Book-Quote prüfen" + the ⚠️ warning and hides the fake EV, and makes
the settlement pipeline invalidate its P/L so the estimated price never
pollutes the stats.

This never fabricates a leg: team and player legs must already exist as
observed rows in the pool. It is gated by PH_ESTIMATED_SAME_GAME_BUILDERS
(the same opt-in as the player-only estimated builders).
"""
from __future__ import annotations
import math
import os
import re
from itertools import combinations

TEAM_MARKET_KEYS = {
    "both_teams_100_points", "game_total_points", "point_spread",
    "alternate_total_points", "alternate_spread", "team_total_points", "team_total",
}


def _g(o, k, d=None):
    return o.get(k, d) if isinstance(o, dict) else getattr(o, k, d)


def _feat(o):
    f = _g(o, "features", {})
    return f if isinstance(f, dict) else {}


def _norm_game(o):
    return re.sub(r"\s+", " ", str(_g(o, "game", "") or "").strip().lower())


def _is_team_leg(row):
    f = _feat(row)
    raw = _g(row, "raw", {}) or (f.get("raw") if isinstance(f.get("raw"), dict) else {}) or {}
    mk = str(_g(row, "market_key", "") or _g(row, "market", "")).lower()
    player = str(_g(row, "player", "") or _g(row, "player_name", "")).strip().upper()
    return (
        bool(raw.get("event_market")) or mk in TEAM_MARKET_KEYS
        or player in {"GAME", ""} or player.startswith("TEAM ")
    ) and mk in TEAM_MARKET_KEYS


def _is_player_leg(row):
    player = str(_g(row, "player", "") or _g(row, "player_name", "")).strip()
    mk = str(_g(row, "market_key", "") or _g(row, "market", "")).lower()
    return bool(player) and player.upper() not in {"GAME"} and not player.upper().startswith("TEAM ") and mk not in TEAM_MARKET_KEYS


def _odds(row):
    try:
        return float(_g(row, "odds", None) if _g(row, "odds", None) is not None else _g(row, "odds_decimal", 0))
    except (TypeError, ValueError):
        return 0.0


def _observed(row):
    f = _feat(row)
    return f.get("odds_observed") is True or _g(row, "odds_observed") is True


def _leg_text(row):
    player = _g(row, "player", "") or _g(row, "player_name", "")
    market = _g(row, "market", "")
    direction = _g(row, "direction", "")
    point = _g(row, "point", None)
    if point is None:
        point = _g(row, "line", None)
    try:
        pt = f"{float(point):g}"
    except (TypeError, ValueError):
        pt = str(point or "")
    return f"{player} {market} {direction} {pt} @{_odds(row):.2f}"


def _leg_detail(row):
    return {
        "player": _g(row, "player", "") or _g(row, "player_name", ""),
        "sport": _g(row, "sport", ""),
        "market": _g(row, "market", ""),
        "direction": _g(row, "direction", ""),
        "point": _g(row, "point", None) if _g(row, "point", None) is not None else _g(row, "line", None),
        "odds": _odds(row),
        "bookmaker": _feat(row).get("bookmaker") or _g(row, "bookmaker", ""),
        "game": _g(row, "game", ""),
    }


def build_estimated_mixed(props, PickCls, max_tickets=4, max_legs=4):
    """Return estimated team+player same-game builders from the observed pool."""
    if os.getenv("PH_ESTIMATED_SAME_GAME_BUILDERS", "0").strip().lower() not in {"1", "true", "yes", "on"}:
        return []
    props = [p for p in (props or []) if _observed(p) and _odds(p) > 1 and _norm_game(p) and "@" in str(_g(p, "game", ""))]

    # Group by game; each ticket is one team leg + 1-3 player legs from that game.
    by_game = {}
    for p in props:
        by_game.setdefault(_norm_game(p), []).append(p)

    out = []
    for game, rows in by_game.items():
        team_legs = [r for r in rows if _is_team_leg(r)]
        player_legs = [r for r in rows if _is_player_leg(r)]
        if not team_legs or len(player_legs) < 1:
            continue
        # Strongest team leg (best implied prob = lowest odds) + top player legs
        team = min(team_legs, key=_odds)
        # Pick up to 3 distinct players so the ticket spreads across the roster.
        seen_players, chosen = set(), []
        for pl in sorted(player_legs, key=_odds):  # safest first
            name = str(_g(pl, "player", "") or _g(pl, "player_name", "")).lower()
            if name in seen_players:
                continue
            seen_players.add(name)
            chosen.append(pl)
            if len(chosen) >= max_legs - 1:
                break
        if not chosen:
            continue

        legs = [team] + chosen
        odds = math.prod(_odds(l) for l in legs)
        if not math.isfinite(odds) or odds <= 1 or odds > 300:
            continue

        pick = PickCls(
            type="betbuilder", category="mixed",
            player=" + ".join(str(_g(l, "player", "") or _g(l, "player_name", "")) for l in legs),
            team="", emoji="🎯",
            market=f"{len(legs)}-Leg TEAM + PLAYER",
            direction="over", odds=round(odds, 2), stake=0.05,
            probability=None, edge_pct=None, ev=None,
            game=_g(team, "game", ""),
            legs=[_leg_text(l) for l in legs],
        )
        pick.sport = str(_g(team, "sport", "") or _g(chosen[0], "sport", "")).upper()
        pick.leg_details = [_leg_detail(l) for l in legs]
        # Estimated price from correlated legs -> flagged, card warns, P/L invalidated.
        pick.features = {
            "odds_observed": True, "price_type": "derived_builder",
            "builder_odds_estimated_from_legs": True, "combo_scope": "same_game",
            "mixed_team_player": True,
            "bookmaker": _feat(team).get("bookmaker") or _g(team, "bookmaker", ""),
        }
        out.append(pick)
        if len(out) >= max_tickets:
            break
    return out
