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
    events = []
    for _ in range(4):  # list feed is flaky: retry until it returns events
        events = _list_events(HOST, SPORT_IDS["NFL"])
        if events:
            break
    nfl = [e for e in events if isinstance(e, dict) and _league_ok("NFL", e)]
    print(f"NFL events: raw={len(events)} nfl={len(nfl)}", flush=True)
    # Prefer a real single game (two team names), skip 'Enhanced Specials'.
    games = [e for e in nfl if "special" not in str(e.get("LE") or e.get("L") or "").lower()]
    for ev in games[:2]:
        eid = ev.get("I") or ev.get("CI")
        teams = f"{ev.get('O1')} vs {ev.get('O2')}"
        print(f"\n=== EVENT {eid}: {teams} ===", flush=True)
        payload = _game(HOST, eid)
        if not payload:
            payload = _game(HOST, eid)  # 22bet often returns empty on first hit
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
            if not subval:
                subval = _game(HOST, sid)  # retry: first hit is often empty
            v = (subval or {}).get("Value") if isinstance(subval, dict) else None
            if not isinstance(v, dict):
                continue
            # Aggregate per type_id: which (player, line, price) triples exist.
            # This reveals the real market per type_id across the WHOLE subgame.
            from collections import defaultdict
            per_type = defaultdict(list)
            for group in v.get("GE") or []:
                if not isinstance(group, dict):
                    continue
                for bucket in group.get("E") or []:
                    for o in (bucket if isinstance(bucket, list) else [bucket]):
                        if not isinstance(o, dict):
                            continue
                        pl = o.get("PL")
                        if not isinstance(pl, dict) or not pl.get("N"):
                            continue
                        per_type[str(o.get("T"))].append(
                            (str(pl.get("N"))[:18], o.get("P"), o.get("C"), o.get("G"))
                        )
            for tid, rows_ in sorted(per_type.items()):
                lines = sorted({r[1] for r in rows_ if r[1] is not None})
                sample = rows_[:3]
                print(f"  SUB '{title}' type {tid}: n={len(rows_)} lines={lines[:10]} sample={sample}", flush=True)


if __name__ == "__main__":
    main()
