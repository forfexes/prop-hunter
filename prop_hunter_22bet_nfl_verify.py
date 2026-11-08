#!/usr/bin/env python3
"""One-shot 22bet NFL verification dump: full raw outcome fields per player prop.

Read-only. Publishes nothing. Prints, per NFL event, every player outcome with
ALL its fields so (type_id, line, price, direction-field) can be matched against
the operator screen to build a verified market+direction mapping.
"""
from __future__ import annotations
import json
from prop_hunter_1xbet import _list_events, _game, _league_ok, SPORT_IDS

HOST = "https://22bet.com/service-api/LineFeed"


def main():
    events = _list_events(HOST, SPORT_IDS["NFL"])
    nfl = [e for e in events if isinstance(e, dict) and _league_ok("NFL", e)]
    print(f"NFL events: raw={len(events)} nfl={len(nfl)}", flush=True)
    # Prefer a real single game (two team names), skip 'Enhanced Specials'.
    games = [e for e in nfl if "special" not in str(e.get("LE") or e.get("L") or "").lower()]
    for ev in games[:2]:
        eid = ev.get("I") or ev.get("CI")
        teams = f"{ev.get('O1')} vs {ev.get('O2')}"
        print(f"\n=== EVENT {eid}: {teams} ===", flush=True)
        payload = _game(HOST, eid)
        val = (payload or {}).get("Value") if isinstance(payload, dict) else None
        if not isinstance(val, dict):
            continue
        for sub in val.get("SG") or []:
            if not isinstance(sub, dict):
                continue
            title = str(sub.get("TG") or sub.get("PN") or sub.get("N") or "")
            if "player" not in title.lower() and "stat" not in title.lower():
                continue
            sid = sub.get("CI") or sub.get("I")
            if not sid:
                continue
            subval = _game(HOST, sid)
            v = (subval or {}).get("Value") if isinstance(subval, dict) else None
            if not isinstance(v, dict):
                continue
            for group in v.get("GE") or []:
                if not isinstance(group, dict):
                    continue
                # Group-level fields may name the market / carry GÜ-GU grouping.
                gmeta = {k: group.get(k) for k in ("G", "GS", "GN", "N", "PN", "Name") if group.get(k) is not None}
                printed = 0
                for bucket in group.get("E") or []:
                    for o in (bucket if isinstance(bucket, list) else [bucket]):
                        if not isinstance(o, dict):
                            continue
                        pl = o.get("PL")
                        if not isinstance(pl, dict) or not pl.get("N"):
                            continue
                        if printed < 6:
                            print(f"  GROUP {gmeta} | OUTCOME {json.dumps(o, ensure_ascii=False)}", flush=True)
                            printed += 1


if __name__ == "__main__":
    main()
