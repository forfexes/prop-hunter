#!/usr/bin/env python3
"""Opt-in 22bet NFL player-prop source. Bounded, observed prices only, fail-closed.

Market mapping verified against the 22bet operator screen for
Atlanta Falcons @ Cincinnati Bengals (2026-11-08), matching player + line +
price in the live app to the LineFeed type_ids:

    type 8397  Passing Yards      (Joe Burrow 149.5/174.5/199.5)
    type 8395  Rushing Yards      (Khalil Herbert 4.5/5.5/6.5/11.5)
    type 8393  Receiving Yards    (Charlie Woerner 5.5/7.5/18.5)
    type 6188  Touchdowns         (Bijan Robinson 0.5 anytime / 1.5+ )

Any type_id NOT in VERIFIED_MARKETS is dropped — no guessed markets ever
reach a pick. Direction is decoded from the outcome label via the shared
1xBet/_direction helper; outcomes whose direction is ambiguous are skipped.
"""
from __future__ import annotations
import math
import os
from datetime import datetime, timezone

from prop_hunter_1xbet import _list_events, _game, _league_ok, _direction, SPORT_IDS

HOST = "https://22bet.com/service-api/LineFeed"

# type_id -> (market_key, market_label). ONLY verified ids. Everything else dropped.
VERIFIED_MARKETS = {
    "8397": ("passing_yards", "Passing Yards"),
    "8395": ("rushing_yards", "Rushing Yards"),
    "8393": ("receiving_yards", "Receiving Yards"),
    "6188": ("touchdowns", "Touchdowns"),
}

# Plausibility guards per market: a line outside the band means the mapping or
# the feed is off, so the outcome is dropped rather than posted wrong.
LINE_BANDS = {
    "passing_yards": (40.0, 400.0),
    "rushing_yards": (2.0, 200.0),
    "receiving_yards": (2.0, 200.0),
    "touchdowns": (0.5, 5.5),
}


def configured() -> bool:
    return os.getenv("PH_22BET_NFL_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")


def _subgame_rows(subval, event):
    value = (subval or {}).get("Value") if isinstance(subval, dict) else None
    if not isinstance(value, dict):
        return []
    observed_at = datetime.now(timezone.utc).isoformat()
    eid = str(event.get("I") or event.get("CI") or "")
    rows = []
    for group in value.get("GE") or []:
        if not isinstance(group, dict):
            continue
        for bucket in group.get("E") or []:
            for e in (bucket if isinstance(bucket, list) else [bucket]):
                if not isinstance(e, dict):
                    continue
                typ = str(e.get("T"))
                mapping = VERIFIED_MARKETS.get(typ)
                if not mapping:
                    continue  # fail-closed: unmapped type_id never posts
                market_key, market_label = mapping
                pl = e.get("PL")
                player = str(pl.get("N") or "").strip() if isinstance(pl, dict) else ""
                if not player:
                    continue
                direction = _direction(e)
                if direction not in {"over", "under"}:
                    continue  # ambiguous direction -> skip, never guess
                try:
                    line = float(e.get("P"))
                    odds = float(e.get("C"))
                except (TypeError, ValueError):
                    continue
                if not math.isfinite(line) or not math.isfinite(odds):
                    continue
                if not (1.01 < odds <= 50):
                    continue
                lo, hi = LINE_BANDS.get(market_key, (0.0, 1e9))
                if not (lo <= line <= hi):
                    continue
                rows.append({
                    "source": "22bet_linefeed", "bookmaker": "22bet", "sport": "NFL", "league": "NFL",
                    "source_event_id": eid, "event_id": eid,
                    "commence_time": str(event.get("S") or ""),
                    "home_team": str(event.get("O1") or ""), "away_team": str(event.get("O2") or ""),
                    "player_name": player, "market": market_label, "market_key": market_key,
                    "direction": direction, "line": line, "odds_decimal": odds,
                    "selection": f"{player} {direction} {line} {market_label.lower()}",
                    "observed_at": observed_at, "odds_observed": True,
                    "raw": {"host": HOST, "type": typ, "player_id": pl.get("I") if isinstance(pl, dict) else None},
                })
    return rows


def fetch_22bet_nfl_props(max_events=3):
    """Return observed NFL player-prop rows from 22bet. Fail-closed when unreachable."""
    if not configured():
        return []
    try:
        events = _list_events(HOST, SPORT_IDS["NFL"])
    except Exception as exc:
        if os.getenv("PH_22BET_DEBUG"): print(f"22bet_nfl: _list_events raised {exc}", flush=True)
        return []
    candidates = [e for e in events if isinstance(e, dict) and _league_ok("NFL", e)]
    if os.getenv("PH_22BET_DEBUG"):
        labels = [str(e.get("LE") or e.get("L") or "")[:30] for e in events[:5] if isinstance(e, dict)]
        print(f"22bet_nfl debug: raw_events={len(events)} after_league_ok={len(candidates)} sample_labels={labels}", flush=True)
    rows = []
    for ev in candidates[:max(1, min(int(max_events), 6))]:
        eid = ev.get("I") or ev.get("CI")
        if not eid:
            continue
        try:
            payload = _game(HOST, eid)
        except Exception:
            continue
        val = (payload or {}).get("Value") if isinstance(payload, dict) else None
        if not isinstance(val, dict):
            continue
        subs = val.get("SG") or []
        if os.getenv("PH_22BET_DEBUG"):
            titles = [str(s.get("TG") or s.get("PN") or s.get("N") or "")[:28] for s in subs if isinstance(s, dict)]
            print(f"22bet_nfl debug: event {eid} subgames={len(subs)} titles={titles[:12]}", flush=True)
        for sub in subs:
            if not isinstance(sub, dict):
                continue
            title = str(sub.get("TG") or sub.get("PN") or sub.get("N") or "").strip().lower()
            if "player" not in title and "stat" not in title:
                continue
            sid = sub.get("CI") or sub.get("I")
            if not sid:
                continue
            try:
                subval = _game(HOST, sid)
            except Exception:
                continue
            rows.extend(_subgame_rows(subval, ev))
    return rows


if __name__ == "__main__":
    print("configured:", configured())
    print("rows:", len(fetch_22bet_nfl_props()))
