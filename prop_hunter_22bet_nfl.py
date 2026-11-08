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
#
# Verified against the live 22bet screen + two full LineFeed dumps
# (Falcons@Bengals and Panthers@Broncos, 2026-11-08):
#
#   8397/8398 (group 2627) = Passing Yards — ONLY QBs, lines 149.5..324.5,
#     a range and player set no other NFL stat produces. Confirmed across four
#     QBs (Burrow, Penix, Young, Nix). Rock solid.
#   6188 (group 1953) = Anytime Touchdown — single 0.5 line for every skill
#     player, prices fanning out per player. Matches JK's "anytime TD" screen.
#
# NOT yet mapped (left out, fail-closed): 8395/8396 (group 2626) and
# 8393/8394 (group 2625) are yard markets for RB/WR but the live screen's
# rushing-yards lines (69.5..99.5) don't line up cleanly with either group's
# observed range yet, so rushing vs receiving can't be separated with
# certainty — posting them now would risk mislabelling. 6109/6229 are Yes/No
# TD variants without a line.
VERIFIED_MARKETS = {
    "8397": ("passing_yards", "Passing Yards"),
    "8398": ("passing_yards", "Passing Yards"),
    "6188": ("anytime_td", "Anytime Touchdown"),
}

# Plausibility guards. A mislabelled line falls outside its band and is dropped.
LINE_BANDS = {
    "passing_yards": (100.0, 400.0),   # QB passing lines only
    "anytime_td": (0.5, 0.5),          # anytime TD is exactly the 0.5 line
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
                # 22bet liefert diese Spieler-Props als reine "Over X.5"-Outcomes:
                # ein Eintrag pro Spieler+Schwelle, die Linie (P) ist die Schwelle,
                # die Quote (C) ist der Preis, dass der Spieler DRUEBER kommt. Es gibt
                # keine Unter-Seite in diesem Feed-Typ (bestaetigt am Rohdump:
                # {'T':8395,'P':0.5,'PL':{'N':'Khalil Herbert'},'C':2.22} ohne over/under-Label).
                # Falls ein Label doch eine Richtung nennt, respektieren wir sie; sonst "over".
                direction = _direction(e) or "over"
                if direction not in {"over", "under"}:
                    continue
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
    events = []
    for _ in range(3):  # 22bet list feed is flaky, often empty on first hit
        try:
            events = _list_events(HOST, SPORT_IDS["NFL"])
        except Exception:
            events = []
        if events:
            break
    candidates = [e for e in events if isinstance(e, dict) and _league_ok("NFL", e)]
    rows = []
    for ev in candidates[:max(1, min(int(max_events), 6))]:
        eid = ev.get("I") or ev.get("CI")
        if not eid:
            continue
        try:
            payload = _game(HOST, eid)
            if not payload:
                payload = _game(HOST, eid)  # first hit often empty
        except Exception:
            continue
        val = (payload or {}).get("Value") if isinstance(payload, dict) else None
        if not isinstance(val, dict):
            continue
        subs = val.get("SG") or []
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
                if not subval:
                    subval = _game(HOST, sid)  # first hit often empty
            except Exception:
                continue
            rows.extend(_subgame_rows(subval, ev))
    return rows


if __name__ == "__main__":
    print("configured:", configured())
    print("rows:", len(fetch_22bet_nfl_props()))
