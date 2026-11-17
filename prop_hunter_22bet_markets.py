#!/usr/bin/env python3
"""22bet multi-sport player-prop parser (verified type_ids only, fail-closed).

Reads the 22bet LineFeed 'Players' stats' subgames across sports and emits
observed player-prop rows. Every market is keyed by a VERIFIED type_id pulled
from the live probe (prop_hunter_22bet_probe) — a 22bet type_id that is not in
the table for its sport is dropped, never guessed, so a mislabelled market can
never reach the pipeline.

Probe evidence (2026-11-16, prop_hunter_22bet_probe output):
  NFL 'Players' stats':
    8395/8396  Unresolved RB yard/threshold market — do not publish
    8397/8398  Passing Yards   (Herbert QB 193.5, Brissett QB 149.5) over/under
    8393/8394  Unresolved receiving/reception market — do not publish
    6188       Anytime TD      (line 0.5, Henry @6.5) yes
  NHL 'Players' stats':
    1444       Shots on Goal   (line 0.5, Caufield @2.15) over (paired 1445 under)
    833        Anytime Goal    (no line, scorer market) yes
    834        Anytime Assist  (no line) yes
  NBA/MLB: no 'Players' stats' subgame was open at probe time (overnight), so
    their type_ids are NOT yet verified and stay unmapped (fail-closed).

Line bands sanity-check each market so a feed glitch can't post an absurd line.
"""
from __future__ import annotations
import math
import os
from datetime import datetime, timezone

# sport -> { type_id(str): (market_key, market_label, direction) }
# direction "over"/"under" for paired lines, "yes" for binary (line usually 0.5).
VERIFIED_MARKETS = {
    # 8393/8394 and 8395/8396 have contradictory mappings in the existing
    # source modules; require operator-side market verification before enabling.
    "NFL": {
        "8397": ("passing_yards", "Passing Yards", "over"),
        "8398": ("passing_yards", "Passing Yards", "under"),
        "6188": ("anytime_td", "Anytime TD", "yes"),
    },
    "NHL": {
        "1444": ("shots_on_goal", "Shots on Goal", "over"),
        "1445": ("shots_on_goal", "Shots on Goal", "under"),
        "833": ("goals", "Anytime Goal", "yes"),
        "834": ("assists", "Anytime Assist", "yes"),
    },
    # NBA/WNBA points are handled by the dedicated points parser until the
    # full NBA type_id set (rebounds/assists/DD/TD) is verified from a probe
    # taken while NBA player props are live. Left intentionally empty here.
    "NBA": {},
    "WNBA": {},
    "MLB": {},
}

# market_key -> (min_line, max_line) plausibility band. Binary ("yes") markets
# use 0.5 and are exempt from the upper band.
LINE_BANDS = {
    "rushing_yards": (0.5, 200.0),
    "passing_yards": (49.5, 450.0),
    "receiving_yards": (0.5, 200.0),
    "receptions": (0.5, 20.0),
    "shots_on_goal": (0.5, 12.0),
    "anytime_td": (0.0, 1.0),
    "goals": (0.0, 1.0),
    "assists": (0.0, 1.0),
    "points": (0.5, 70.0),
    "rebounds": (0.5, 30.0),
}


def _finite(*xs) -> bool:
    try:
        return all(math.isfinite(float(x)) for x in xs)
    except (TypeError, ValueError):
        return False


def _band_ok(market_key: str, line) -> bool:
    band = LINE_BANDS.get(market_key)
    if not band:
        return True
    try:
        lo, hi = band
        return lo <= float(line) <= hi
    except (TypeError, ValueError):
        return False


def parse_players_stats(sub_value, event, sport, host="https://22bet.com"):
    """Parse one 'Players' stats' subgame into observed prop rows.

    sub_value: the LineFeed Value dict of a subgame (has 'GE' groups).
    event: the parent event dict (teams, commence time, id).
    sport: Prop Hunter sport label (e.g. 'NFL').
    """
    table = VERIFIED_MARKETS.get(str(sport).upper())
    if not table:
        return []
    value = (sub_value or {}).get("Value") if isinstance(sub_value, dict) else sub_value
    if not isinstance(value, dict):
        return []
    groups = value.get("GE") or []
    if not isinstance(groups, list):
        return []
    observed_at = datetime.now(timezone.utc).isoformat()
    eid = str(event.get("I") or event.get("CI") or "")
    home = str(event.get("O1") or "")
    away = str(event.get("O2") or "")
    commence = str(event.get("S") or "")
    out = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        for bucket in group.get("E") or []:
            for e in (bucket if isinstance(bucket, list) else [bucket]):
                if not isinstance(e, dict):
                    continue
                typ = str(e.get("T"))
                mapping = table.get(typ)
                if not mapping:
                    continue  # fail-closed: unverified type dropped
                market_key, market_label, direction = mapping
                pl = e.get("PL")
                if not isinstance(pl, dict):
                    continue  # player-named outcomes only
                player = str(pl.get("N") or "").strip()
                if not player:
                    continue
                try:
                    odds = float(e.get("C"))
                except (TypeError, ValueError):
                    continue
                if not (1.01 < odds <= 51):
                    continue
                # Binary markets ("yes") may carry a 0.5 line or none.
                if direction == "yes":
                    line = 0.5
                else:
                    raw_line = e.get("P")
                    if raw_line is None or not _finite(raw_line):
                        continue
                    line = float(raw_line)
                    if line < 0:
                        continue
                if not _band_ok(market_key, line):
                    continue
                out.append({
                    "source": "22bet_linefeed", "bookmaker": "22bet",
                    "sport": str(sport).upper(), "league": str(sport).upper(),
                    "source_event_id": eid, "event_id": eid,
                    "commence_time": commence, "home_team": home, "away_team": away,
                    "player_name": player, "market": market_key, "market_key": market_key,
                    "market_label": market_label, "direction": direction,
                    "line": line, "odds_decimal": odds,
                    "selection": f"{player} {direction} {line} {market_label}",
                    "observed_at": observed_at, "odds_observed": True,
                    "raw": {"host": host, "type": typ, "player_id": pl.get("I")},
                })
    return out
