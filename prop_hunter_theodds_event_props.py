#!/usr/bin/env python3
"""
PROP HUNTER — THE ODDS API EVENT PLAYER PROPS LOADER
====================================================

Final Fix für:
- Events vorhanden, aber props: 0
- The Odds API Player Props müssen eventweise geladen werden:
  /sports/{sport}/events/{eventId}/odds
- Key-Rotation: nutzt Keys mit höchster Rest-Quota zuerst.
- Ein Market nach dem anderen, damit 422/Market-Mix-Probleme vermieden werden.
- Speichert lokale Datei:
  prop_hunter_event_props_cache.json
- Speichert optional Supabase:
  prop_hunter_prop_snapshots

Env:
ODDS_API_KEY oder ODDS_API_KEYS
SUPABASE_URL
SUPABASE_KEY
ODDS_REGIONS=us,eu
ODDS_EVENT_LIMIT_PER_SPORT=20
ODDS_MARKET_SLEEP=0.05
"""

from __future__ import annotations

import os
import re
import json
import time
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests

try:
    from supabase import create_client
except Exception:
    create_client = None

BASE = "https://api.the-odds-api.com/v4"
OUT_FILE = Path("prop_hunter_event_props_cache.json")
TIMEOUT = int(os.getenv("ODDS_TIMEOUT", "25"))

SPORTS = [
    "baseball_mlb",
    "basketball_wnba",
    "basketball_nba",
    "americanfootball_nfl",
]

SPORT_LABEL = {
    "baseball_mlb": ("BASEBALL", "MLB"),
    "basketball_wnba": ("BASKETBALL", "WNBA"),
    "basketball_nba": ("BASKETBALL", "NBA"),
    "americanfootball_nfl": ("AMERICAN_FOOTBALL", "NFL"),
}

SPORT_MARKETS = {
    "baseball_mlb": [
        "batter_home_runs",
        "batter_hits",
        "batter_total_bases",
        "batter_rbis",
        "batter_runs_scored",
        "batter_stolen_bases",
        "pitcher_strikeouts",
        "pitcher_record_a_win",
    ],
    "basketball_wnba": [
        "player_points",
        "player_rebounds",
        "player_assists",
        "player_threes",
        "player_blocks",
        "player_steals",
        "player_turnovers",
        "player_rebounds_assists",
        "player_points_rebounds_assists",
        "player_points_rebounds",
        "player_points_assists",
    ],
    "basketball_nba": [
        "player_points",
        "player_rebounds",
        "player_assists",
        "player_threes",
        "player_blocks",
        "player_steals",
        "player_turnovers",
        "player_rebounds_assists",
        "player_points_rebounds_assists",
        "player_points_rebounds",
        "player_points_assists",
    ],
    "americanfootball_nfl": [
        "player_anytime_td",
        "player_1st_td",
        "player_last_td",
        "player_pass_tds",
        "player_pass_yds",
        "player_pass_completions",
        "player_pass_attempts",
        "player_pass_interceptions",
        "player_rush_yds",
        "player_rush_attempts",
        "player_receptions",
        "player_reception_yds",
        "player_kicking_points",
    ],
}


def log(msg: str) -> None:
    print(datetime.now().strftime("%H:%M:%S"), "INFO   ", msg, flush=True)


def warn(msg: str) -> None:
    print(datetime.now().strftime("%H:%M:%S"), "WARNING", msg, flush=True)


def norm_name(s: Any) -> str:
    s = str(s or "").strip().lower()
    s = re.sub(r"[^a-z0-9\s\.\-']", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def market_group(market: str) -> str:
    m = str(market or "").lower()
    if "home_run" in m:
        return "HR"
    if "hits" in m and "allowed" not in m:
        return "HITS"
    if "total_bases" in m:
        return "TOTAL_BASES"
    if "rbis" in m:
        return "RBI"
    if "runs_scored" in m:
        return "RUNS"
    if "stolen" in m:
        return "STOLEN_BASES"
    if "pitcher_strikeouts" in m:
        return "PITCHER_K"
    if "points_rebounds_assists" in m:
        return "PRA"
    if "rebounds_assists" in m:
        return "RA"
    if "points_rebounds" in m:
        return "PR"
    if "points_assists" in m:
        return "PA"
    if "points" in m:
        return "POINTS"
    if "rebounds" in m:
        return "REBOUNDS"
    if "assists" in m:
        return "ASSISTS"
    if "threes" in m:
        return "THREES"
    if "anytime_td" in m:
        return "ANYTIME_TD"
    if "1st_td" in m:
        return "FIRST_TD"
    if "reception_yds" in m:
        return "RECEIVING_YARDS"
    if "receptions" in m:
        return "RECEPTIONS"
    if "rush_yds" in m:
        return "RUSHING_YARDS"
    if "pass_yds" in m:
        return "PASSING_YARDS"
    return m.upper()


def to_float(x: Any) -> Optional[float]:
    try:
        if x is None or x == "":
            return None
        return float(x)
    except Exception:
        return None


def implied_prob(decimal_odds: Any) -> Optional[float]:
    odds = to_float(decimal_odds)
    if not odds or odds <= 1:
        return None
    return 1.0 / odds


def hash_key(*parts: Any) -> str:
    raw = "|".join(str(p or "") for p in parts)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def get_keys() -> List[str]:
    raw = os.getenv("ODDS_API_KEYS", "").strip() or os.getenv("ODDS_API_KEY", "").strip()
    return [x.strip() for x in raw.replace("\n", ",").split(",") if x.strip()]


def mask(k: str) -> str:
    if len(k) <= 8:
        return k[:2] + "***"
    return k[:4] + "***" + k[-4:]


def request_json(url: str, params: dict) -> Tuple[int, Any, Dict[str, str], str]:
    try:
        r = requests.get(url, params=params, timeout=TIMEOUT)
        try:
            data = r.json()
        except Exception:
            data = None
        headers = {
            "remaining": r.headers.get("x-requests-remaining", ""),
            "used": r.headers.get("x-requests-used", ""),
            "last": r.headers.get("x-requests-last", ""),
        }
        return r.status_code, data, headers, r.text[:500]
    except Exception as e:
        return 0, None, {}, str(e)


def key_status(key: str) -> dict:
    status, data, headers, text = request_json(f"{BASE}/sports", {"apiKey": key})
    try:
        remaining = int(headers.get("remaining") or -1)
    except Exception:
        remaining = -1
    return {"key": key, "status": status, "remaining": remaining, "headers": headers, "text": text}


def sorted_working_keys() -> List[str]:
    keys = get_keys()
    infos = [key_status(k) for k in keys]
    for i, info in enumerate(infos, start=1):
        log(f"ODDS KEY {i}/{len(infos)} {mask(info['key'])}: status={info['status']} remaining={info['remaining']}")
    working = [x for x in infos if x["status"] == 200 and x["remaining"] != 0]
    working.sort(key=lambda x: x["remaining"], reverse=True)
    return [x["key"] for x in working]


def api_get_with_rotation(keys: List[str], url: str, params: dict) -> Tuple[int, Any, dict, str, Optional[str]]:
    last = (0, None, {}, "no keys", None)
    for key in keys:
        p = dict(params)
        p["apiKey"] = key
        status, data, headers, text = request_json(url, p)
        last = (status, data, headers, text, key)
        if status == 200:
            return last
        if status in (401, 403, 429):
            warn(f"key {mask(key)} status={status} remaining={headers.get('remaining')}; rotate")
            continue
        if status == 422:
            # market not available / invalid for this endpoint; do not rotate forever
            return last
    return last


def fetch_events(keys: List[str], sport_key: str) -> List[dict]:
    status, data, headers, text, key = api_get_with_rotation(keys, f"{BASE}/sports/{sport_key}/events", {})
    if status != 200:
        warn(f"{sport_key}: events failed status={status} text={text[:160]}")
        return []
    if not isinstance(data, list):
        return []
    return data


def parse_event_market(sport_key: str, event: dict, market: str, data: Any, source_key_masked: str) -> List[dict]:
    if not isinstance(data, dict):
        return []
    sport, league = SPORT_LABEL.get(sport_key, ("UNKNOWN", sport_key.upper()))
    rows = []
    event_id = data.get("id") or event.get("id")
    commence_time = data.get("commence_time") or event.get("commence_time")
    home_team = data.get("home_team") or event.get("home_team")
    away_team = data.get("away_team") or event.get("away_team")
    game = f"{away_team} @ {home_team}" if home_team and away_team else ""

    for bookmaker in data.get("bookmakers", []) or []:
        book = bookmaker.get("key") or bookmaker.get("title") or bookmaker.get("name")
        for mk in bookmaker.get("markets", []) or []:
            market_key = mk.get("key") or market
            for out in mk.get("outcomes", []) or []:
                name = out.get("description") or out.get("name") or out.get("player") or ""
                direction = out.get("name") if out.get("description") else None
                # The Odds API usually: name=Over/Under, description=player
                if str(name).lower() in ("over", "under") and out.get("description"):
                    name = out.get("description")
                if not name:
                    continue
                price = to_float(out.get("price"))
                line = to_float(out.get("point"))
                direction = direction or out.get("name")

                snapshot_id = hash_key(
                    "the_odds_api_event_props",
                    sport_key,
                    event_id,
                    book,
                    market_key,
                    name,
                    direction,
                    line,
                    price,
                )
                rows.append({
                    "snapshot_id": snapshot_id,
                    "snapshot_ts": datetime.now(timezone.utc).isoformat(),
                    "source": "the_odds_api_event_props",
                    "sport": sport,
                    "league": league,
                    "source_sport_key": sport_key,
                    "source_event_id": event_id,
                    "event_id": event_id,
                    "game_id": event_id,
                    "commence_time": commence_time,
                    "game": game,
                    "home_team": home_team,
                    "away_team": away_team,
                    "player_name": name,
                    "normalized_name": norm_name(name),
                    "market": market_key,
                    "market_key": market_key,
                    "market_group": market_group(market_key),
                    "direction": direction,
                    "line": line,
                    "odds": price,
                    "odds_decimal": price,
                    "bookmaker": book,
                    "implied_prob": implied_prob(price),
                    "source_confidence": 0.95,
                    "raw": {
                        "outcome": out,
                        "bookmaker": bookmaker,
                        "market": mk,
                        "key_used": source_key_masked,
                    },
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })
    return rows


def fetch_event_market(keys: List[str], sport_key: str, event: dict, market: str, regions: str) -> List[dict]:
    eid = event.get("id")
    if not eid:
        return []
    params = {
        "regions": regions,
        "markets": market,
        "oddsFormat": "decimal",
        "dateFormat": "iso",
    }
    status, data, headers, text, key = api_get_with_rotation(
        keys,
        f"{BASE}/sports/{sport_key}/events/{eid}/odds",
        params,
    )
    if status == 200:
        rows = parse_event_market(sport_key, event, market, data, mask(key or ""))
        log(f"{sport_key} {market}: event={eid[:8]} rows={len(rows)} remaining={headers.get('remaining')}")
        return rows
    if status not in (404, 422):
        warn(f"{sport_key} {market}: event={eid[:8]} status={status} text={text[:140]}")
    return []


def sb_client():
    if create_client is None:
        return None
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    if not url or not key:
        return None
    try:
        return create_client(url, key)
    except Exception as e:
        warn(f"Supabase client failed: {e}")
        return None


def save_supabase(rows: List[dict]) -> int:
    if not rows:
        return 0
    sb = sb_client()
    if sb is None:
        warn("Supabase missing; skip prop snapshots save")
        return 0
    saved = 0
    batch_size = int(os.getenv("ODDS_SAVE_BATCH_SIZE", "100"))
    for i in range(0, len(rows), batch_size):
        part = rows[i:i + batch_size]
        try:
            sb.table("prop_hunter_prop_snapshots").upsert(part, on_conflict="snapshot_id").execute()
            saved += len(part)
            log(f"prop_hunter_prop_snapshots saved {saved}/{len(rows)}")
            time.sleep(0.1)
        except Exception as e:
            warn(f"save batch failed {i}-{i+len(part)}: {e}")
    return saved


def fetch_all_event_props() -> List[dict]:
    regions = os.getenv("ODDS_REGIONS", "us,eu")
    limit = int(os.getenv("ODDS_EVENT_LIMIT_PER_SPORT", "20"))
    sleep_s = float(os.getenv("ODDS_MARKET_SLEEP", "0.05"))

    keys = sorted_working_keys()
    if not keys:
        warn("No working Odds API keys")
        return []

    all_rows: List[dict] = []
    for sport_key in SPORTS:
        events = fetch_events(keys, sport_key)
        log(f"{sport_key}: events={len(events)}")
        for event in events[:limit]:
            for market in SPORT_MARKETS.get(sport_key, []):
                rows = fetch_event_market(keys, sport_key, event, market, regions)
                all_rows.extend(rows)
                time.sleep(sleep_s)

    # dedup
    dedup = {}
    for r in all_rows:
        dedup[r["snapshot_id"]] = r
    rows = list(dedup.values())
    return rows


def main() -> None:
    log("=" * 60)
    log("PROP HUNTER THE ODDS API EVENT PROPS LOADER")
    log("=" * 60)

    rows = fetch_all_event_props()
    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "count": len(rows),
        "props": rows,
    }
    OUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"wrote {OUT_FILE} rows={len(rows)}")

    saved = save_supabase(rows)
    log(f"supabase saved={saved}/{len(rows)}")
    log("event props loader done")


if __name__ == "__main__":
    main()
