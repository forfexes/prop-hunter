#!/usr/bin/env python3
"""
PROP HUNTER — ODDS DIAGNOSTIC V2
Tests all The Odds API keys for event-level player prop access.
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
OUT = Path("prop_hunter_odds_diagnostic_v2_report.json")

SPORTS = ["baseball_mlb", "basketball_wnba", "basketball_nba", "americanfootball_nfl"]

SPORT_MARKETS = {
    "baseball_mlb": ["batter_home_runs", "batter_hits", "batter_total_bases", "pitcher_strikeouts"],
    "basketball_wnba": ["player_points", "player_rebounds", "player_assists", "player_points_rebounds_assists", "player_rebounds_assists"],
    "basketball_nba": ["player_points", "player_rebounds", "player_assists", "player_points_rebounds_assists", "player_rebounds_assists"],
    "americanfootball_nfl": ["player_anytime_td", "player_reception_yds", "player_rush_yds", "player_pass_yds"],
}


def log(msg: str) -> None:
    print(datetime.now().strftime("%H:%M:%S"), msg, flush=True)


def get_keys() -> List[str]:
    raw = os.getenv("ODDS_API_KEYS", "").strip() or os.getenv("ODDS_API_KEY", "").strip()
    return [x.strip() for x in raw.replace("\n", ",").split(",") if x.strip()]


def masked(k: str) -> str:
    return k[:4] + "***" + k[-4:] if len(k) > 8 else k[:2] + "***"


def req(url: str, params: dict, timeout: int = 25) -> Dict[str, Any]:
    try:
        r = requests.get(url, params=params, timeout=timeout)
        try:
            data = r.json()
        except Exception:
            data = None
        return {
            "status": r.status_code,
            "data": data,
            "text": r.text[:800],
            "headers": {
                "remaining": r.headers.get("x-requests-remaining"),
                "used": r.headers.get("x-requests-used"),
                "last": r.headers.get("x-requests-last"),
            },
        }
    except Exception as e:
        return {"status": "EXCEPTION", "error": str(e), "data": None, "headers": {}}


def remaining_int(headers: dict) -> int:
    try:
        return int(headers.get("remaining") or -1)
    except Exception:
        return -1


def count_outcomes(data: Any) -> int:
    events = [data] if isinstance(data, dict) else data if isinstance(data, list) else []
    total = 0
    for ev in events:
        if not isinstance(ev, dict):
            continue
        for bm in ev.get("bookmakers", []) or []:
            for mk in bm.get("markets", []) or []:
                total += len(mk.get("outcomes", []) or [])
    return total


def get_first_event(key: str, sport: str):
    res = req(f"{BASE}/sports/{sport}/events", {"apiKey": key})
    data = res.get("data")
    events = data if isinstance(data, list) else []
    return res, events[0] if events else None


def test_event_props(key: str, sport: str, event_id: str, markets: List[str], regions: str) -> dict:
    return req(
        f"{BASE}/sports/{sport}/events/{event_id}/odds",
        {
            "apiKey": key,
            "regions": regions,
            "markets": ",".join(markets),
            "oddsFormat": "decimal",
            "dateFormat": "iso",
        },
    )


def main() -> None:
    keys = get_keys()
    regions = os.getenv("ODDS_REGIONS", "us,eu")
    report = {"created_at": datetime.now(timezone.utc).isoformat(), "regions": regions, "keys": [], "tests": []}

    log("=" * 80)
    log("PROP HUNTER ODDS DIAGNOSTIC V2")
    log("=" * 80)

    if not keys:
        log("NO ODDS API KEYS FOUND")
        OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return

    key_infos = []
    for idx, key in enumerate(keys, start=1):
        res = req(f"{BASE}/sports", {"apiKey": key})
        info = {
            "index": idx,
            "masked": masked(key),
            "status": res.get("status"),
            "remaining": remaining_int(res.get("headers") or {}),
            "used": (res.get("headers") or {}).get("used"),
        }
        key_infos.append((key, info))
        report["keys"].append(info)
        log(f"KEY {idx}: {info['masked']} status={info['status']} remaining={info['remaining']} used={info['used']}")

    valid = [(k, i) for k, i in key_infos if i["status"] == 200]
    valid.sort(key=lambda x: x[1]["remaining"], reverse=True)
    log("-" * 80)
    if valid:
        log(f"BEST QUOTA KEY: {valid[0][1]['index']} {valid[0][1]['masked']} remaining={valid[0][1]['remaining']}")

    for key, info in valid:
        log("-" * 80)
        log(f"TEST KEY {info['index']} {info['masked']}")
        for sport in SPORTS:
            ev_res, ev = get_first_event(key, sport)
            event_count = len(ev_res.get("data") or []) if isinstance(ev_res.get("data"), list) else 0
            log(f"{sport}: events_status={ev_res.get('status')} events={event_count}")
            row = {"key": info, "sport": sport, "events_status": ev_res.get("status"), "events_count": event_count, "event": None, "market_tests": []}
            if not ev:
                report["tests"].append(row)
                continue

            row["event"] = {"id": ev.get("id"), "home": ev.get("home_team"), "away": ev.get("away_team")}
            log(f"  event {ev.get('away_team')} @ {ev.get('home_team')} id={ev.get('id')}")

            markets = SPORT_MARKETS.get(sport, [])
            for market in markets:
                res = test_event_props(key, sport, ev.get("id"), [market], regions)
                outcomes = count_outcomes(res.get("data"))
                row["market_tests"].append({
                    "market": market,
                    "status": res.get("status"),
                    "outcomes": outcomes,
                    "text": res.get("text"),
                    "headers": res.get("headers"),
                })
                log(f"    {market}: status={res.get('status')} outcomes={outcomes} remaining={(res.get('headers') or {}).get('remaining')}")
                time.sleep(0.15)

            report["tests"].append(row)
            time.sleep(0.2)

    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log("=" * 80)
    log(f"wrote {OUT}")
    log("diagnostic v2 done")


if __name__ == "__main__":
    main()
