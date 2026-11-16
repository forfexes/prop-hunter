#!/usr/bin/env python3
"""22bet multi-sport collector: pull verified player props for every sport.

Walks the 22bet LineFeed for each configured sport, opens the 'Players' stats'
subgames, and parses them with prop_hunter_22bet_markets (verified type_ids,
fail-closed). This is the broad counterpart to prop_hunter_22bet (NBA points
only); together they feed observed 22bet prices into the pipeline.

Opt-in via PH_22BET_ALL_ENABLED. Bounded per sport so a run stays fast and the
LineFeed isn't hammered. Flaky feed: subgame fetches are retried once.
"""
from __future__ import annotations
import os
import time

from prop_hunter_1xbet import _list_events, _game, _league_ok, SPORT_IDS
from prop_hunter_22bet_markets import parse_players_stats, VERIFIED_MARKETS

HOST = "https://22bet.com/service-api/LineFeed"

# Which sports to sweep, in priority order. Only sports with a verified market
# table actually emit rows; the rest are skipped cheaply.
SPORTS = ["NFL", "NHL", "NBA", "WNBA", "MLB"]


def configured() -> bool:
    return os.getenv("PH_22BET_ALL_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")


def _retry_game(host, gid, tries=2):
    """LineFeed is flaky and often returns empty on the first hit."""
    for i in range(tries):
        payload = _game(host, gid)
        val = (payload or {}).get("Value") if isinstance(payload, dict) else None
        if isinstance(val, dict) and (val.get("GE") or val.get("SG")):
            return payload
        if i + 1 < tries:
            time.sleep(0.4)
    return payload


def fetch_22bet_all(max_events_per_sport=3):
    if not configured():
        return []
    cap = max(1, min(int(os.getenv("PH_22BET_ALL_MAX_EVENTS", str(max_events_per_sport))), 8))
    sub_cap = max(1, min(int(os.getenv("PH_22BET_ALL_MAX_SUBGAMES", "12")), 30))
    rows = []
    for sport in SPORTS:
        if not VERIFIED_MARKETS.get(sport.upper()):
            continue  # no verified markets for this sport yet -> skip
        sid = SPORT_IDS.get(sport)
        if not sid:
            continue
        try:
            events = _list_events(HOST, sid)
        except Exception:
            continue
        candidates = [e for e in events if isinstance(e, dict) and _league_ok(sport, e)]
        for ev in candidates[:cap]:
            eid = ev.get("I") or ev.get("CI")
            if not eid:
                continue
            payload = _retry_game(HOST, eid)
            val = (payload or {}).get("Value") if isinstance(payload, dict) else None
            if not isinstance(val, dict):
                continue
            seen_sub = 0
            for sub in val.get("SG") or []:
                if not isinstance(sub, dict):
                    continue
                title = str(sub.get("TG") or sub.get("PN") or sub.get("N") or "").strip().lower()
                if "stat" not in title and "player" not in title:
                    continue
                sid2 = sub.get("CI") or sub.get("I")
                if not sid2:
                    continue
                sub_payload = _retry_game(HOST, sid2)
                try:
                    rows.extend(parse_players_stats(sub_payload, ev, sport, HOST))
                except Exception:
                    pass
                seen_sub += 1
                if seen_sub >= sub_cap:
                    break
    return rows


if __name__ == "__main__":
    import json
    os.environ.setdefault("PH_22BET_ALL_ENABLED", "1")
    r = fetch_22bet_all()
    from collections import Counter
    print(f"22bet all: {len(r)} rows")
    print("by sport/market:", dict(Counter(f"{x['sport']}/{x['market']}" for x in r)))
    print(json.dumps(r[:6], indent=2))
