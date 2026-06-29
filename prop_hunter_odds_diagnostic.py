#!/usr/bin/env python3
"""
PROP HUNTER — ODDS DIAGNOSTIC
=============================

Diagnose für:
- Events vorhanden, aber props: 0
- The Odds API Key/Quota/Markets/Regions
- Event Player Props Endpoint

Env:
ODDS_API_KEY oder ODDS_API_KEYS
ODDS_REGIONS default=us,eu
ODDS_BOOKMAKERS optional
ODDS_MARKETS default=player_points,player_rebounds,player_assists,player_threes,player_blocks,player_steals,player_turnovers,player_rebounds_assists,player_points_rebounds_assists,batter_home_runs,batter_hits,batter_total_bases,batter_rbis,pitcher_strikeouts
"""

from __future__ import annotations

import os
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import requests

BASE = "https://api.the-odds-api.com/v4"
OUT = Path("prop_hunter_odds_diagnostic_report.json")

SPORTS = [
    "baseball_mlb",
    "basketball_nba",
    "basketball_wnba",
    "americanfootball_nfl",
]

DEFAULT_MARKETS = [
    "player_points",
    "player_rebounds",
    "player_assists",
    "player_threes",
    "player_blocks",
    "player_steals",
    "player_turnovers",
    "player_rebounds_assists",
    "player_points_rebounds_assists",
    "batter_home_runs",
    "batter_hits",
    "batter_total_bases",
    "batter_rbis",
    "pitcher_strikeouts",
]


def log(msg: str):
    print(datetime.now().strftime("%H:%M:%S"), msg, flush=True)


def get_keys() -> List[str]:
    raw = os.getenv("ODDS_API_KEYS", "").strip() or os.getenv("ODDS_API_KEY", "").strip()
    keys = []
    for part in raw.replace("\n", ",").split(","):
        k = part.strip()
        if k:
            keys.append(k)
    return keys


def masked(k: str) -> str:
    if not k:
        return ""
    if len(k) <= 8:
        return k[:2] + "***"
    return k[:4] + "***" + k[-4:]


def request_json(url: str, params: dict, timeout: int = 25):
    try:
        r = requests.get(url, params=params, timeout=timeout)
        text = r.text[:500]
        try:
            data = r.json()
        except Exception:
            data = None
        return {
            "status": r.status_code,
            "headers": {
                "x-requests-remaining": r.headers.get("x-requests-remaining"),
                "x-requests-used": r.headers.get("x-requests-used"),
                "x-requests-last": r.headers.get("x-requests-last"),
            },
            "data": data,
            "text": text,
            "url": r.url.replace(params.get("apiKey", ""), "***") if params.get("apiKey") else r.url,
        }
    except Exception as e:
        return {"status": "EXCEPTION", "error": str(e), "data": None}


def count_props(events_data: Any) -> int:
    total = 0
    if not isinstance(events_data, list):
        return 0
    for ev in events_data:
        for bm in ev.get("bookmakers", []) or []:
            for mk in bm.get("markets", []) or []:
                total += len(mk.get("outcomes", []) or [])
    return total


def main():
    keys = get_keys()
    regions = os.getenv("ODDS_REGIONS", "us,eu")
    bookmakers = os.getenv("ODDS_BOOKMAKERS", "").strip()
    markets = os.getenv("ODDS_MARKETS", ",".join(DEFAULT_MARKETS))

    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "regions": regions,
        "bookmakers": bookmakers,
        "markets": markets,
        "keys": [],
        "sports": {},
    }

    if not keys:
        log("NO ODDS_API_KEY / ODDS_API_KEYS FOUND")
        OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return

    log("=" * 70)
    log("PROP HUNTER ODDS DIAGNOSTIC")
    log("=" * 70)
    log(f"keys: {len(keys)}")
    log(f"regions: {regions}")
    log(f"bookmakers: {bookmakers or '(default)'}")
    log(f"markets: {markets}")

    active_key = None

    # 1) Usage check via sports endpoint
    for i, key in enumerate(keys, start=1):
        res = request_json(f"{BASE}/sports", {"apiKey": key})
        info = {
            "index": i,
            "masked": masked(key),
            "status": res.get("status"),
            "headers": res.get("headers"),
        }
        report["keys"].append(info)

        log(f"KEY {i}/{len(keys)} {masked(key)} → status={res.get('status')} remaining={res.get('headers',{}).get('x-requests-remaining')} used={res.get('headers',{}).get('x-requests-used')}")

        if res.get("status") == 200 and active_key is None:
            active_key = key

    if not active_key:
        log("NO WORKING ODDS KEY FOUND")
        OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return

    log(f"active key: {masked(active_key)}")

    # 2) Check events and player props per sport
    for sport in SPORTS:
        log("-" * 70)
        log(f"SPORT {sport}")
        sport_report = {"events_status": None, "events_count": 0, "props_status": None, "props_count": 0, "events": []}

        # Events
        ev_res = request_json(
            f"{BASE}/sports/{sport}/events",
            {"apiKey": active_key},
        )
        sport_report["events_status"] = ev_res.get("status")
        events = ev_res.get("data") if isinstance(ev_res.get("data"), list) else []
        sport_report["events_count"] = len(events)
        log(f"{sport}: events status={ev_res.get('status')} count={len(events)} remaining={ev_res.get('headers',{}).get('x-requests-remaining')}")

        # Try normal odds endpoint with player markets
        params = {
            "apiKey": active_key,
            "regions": regions,
            "markets": markets,
            "oddsFormat": "decimal",
            "dateFormat": "iso",
        }
        if bookmakers:
            params["bookmakers"] = bookmakers

        odds_res = request_json(f"{BASE}/sports/{sport}/odds", params)
        data = odds_res.get("data")
        props_count = count_props(data)
        sport_report["props_status"] = odds_res.get("status")
        sport_report["props_count"] = props_count
        sport_report["props_text"] = odds_res.get("text")
        log(f"{sport}: sport odds props status={odds_res.get('status')} props_outcomes={props_count} remaining={odds_res.get('headers',{}).get('x-requests-remaining')}")

        # Event-level props for first few events
        for ev in events[:5]:
            eid = ev.get("id")
            home = ev.get("home_team")
            away = ev.get("away_team")
            event_row = {"id": eid, "home": home, "away": away, "event_props_status": None, "event_props_count": 0}
            if eid:
                eparams = dict(params)
                evp = request_json(f"{BASE}/sports/{sport}/events/{eid}/odds", eparams)
                event_row["event_props_status"] = evp.get("status")
                event_row["event_props_count"] = count_props(evp.get("data") if isinstance(evp.get("data"), list) else [evp.get("data")] if isinstance(evp.get("data"), dict) else [])
                event_row["text"] = evp.get("text")
                log(f"  event {eid} {away} @ {home}: status={event_row['event_props_status']} props={event_row['event_props_count']}")
                time.sleep(0.2)
            sport_report["events"].append(event_row)

        report["sports"][sport] = sport_report

    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log("=" * 70)
    log(f"wrote {OUT}")
    log("diagnostic done")


if __name__ == "__main__":
    main()
