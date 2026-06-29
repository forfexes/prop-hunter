#!/usr/bin/env python3
"""
PROP HUNTER V10 HISTORY SCRAPER — BATCH SAFE
============================================

Fix:
- Supabase Free bricht große Upserts ab: statement timeout.
- Speichert History in kleinen Batches.
"""

from __future__ import annotations

import os
import re
import json
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

try:
    from supabase import create_client
except Exception:
    create_client = None

CACHE_FILE = Path("prop_hunter_data_cache.json")
TIMEOUT = 20


def log(msg: str) -> None:
    print(datetime.now().strftime("%H:%M:%S"), "INFO   ", msg, flush=True)


def warn(msg: str) -> None:
    print(datetime.now().strftime("%H:%M:%S"), "WARNING", msg, flush=True)


def norm_name(s: Any) -> str:
    s = str(s or "").lower().strip()
    s = re.sub(r"[^a-z0-9\s\.\-']", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def to_num(x: Any):
    try:
        if x is None or x == "":
            return None
        return float(x)
    except Exception:
        return None


def innings_to_float(x: Any):
    try:
        s = str(x)
        if "." not in s:
            return float(s)
        a, b = s.split(".", 1)
        return float(a) + float(b) / 3.0
    except Exception:
        return None


def sb_client():
    if create_client is None:
        return None
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    if not url or not key:
        return None
    return create_client(url, key)


def chunks(rows: List[Dict[str, Any]], size: int):
    for i in range(0, len(rows), size):
        yield rows[i:i + size]


def batch_upsert(table: str, rows: List[Dict[str, Any]], conflict: str, batch_size: int = 75) -> int:
    if not rows:
        return 0

    try:
        sb = sb_client()
    except Exception as e:
        warn(f"Supabase client failed: {e}")
        return 0

    if sb is None:
        warn(f"Supabase missing; skipped save {table} rows={len(rows)}")
        return 0

    saved = 0
    batch_size = max(10, int(batch_size or 75))

    for batch_no, part in enumerate(chunks(rows, batch_size), start=1):
        try:
            sb.table(table).upsert(part, on_conflict=conflict).execute()
            saved += len(part)
            if batch_no % 10 == 0 or saved == len(rows):
                log(f"{table}: saved {saved}/{len(rows)}")
            time.sleep(float(os.getenv("HISTORY_SAVE_SLEEP", "0.15")))
        except Exception as e:
            warn(f"{table} batch {batch_no} failed size={len(part)}: {e}")
            if len(part) > 10:
                smaller = max(10, len(part) // 3)
                warn(f"retry smaller batches size={smaller}")
                saved += batch_upsert(table, part, conflict, smaller)
            else:
                for one in part:
                    try:
                        sb.table(table).upsert([one], on_conflict=conflict).execute()
                        saved += 1
                        time.sleep(0.05)
                    except Exception as e2:
                        warn(f"single row skipped: {e2}")
    return saved


def http_json(url: str, params: Optional[dict] = None):
    try:
        r = requests.get(
            url,
            params=params or {},
            headers={"User-Agent": "PropHunterHistoryBatchSafe/1.0"},
            timeout=TIMEOUT,
        )
        if r.status_code >= 400:
            warn(f"HTTP {r.status_code}: {url}")
            return None
        return r.json()
    except Exception as e:
        warn(f"HTTP failed {url}: {e}")
        return None


def load_cache() -> dict:
    if not CACHE_FILE.exists():
        warn("DATA+ cache missing: prop_hunter_data_cache.json")
        return {}
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        warn(f"cache read failed: {e}")
        return {}


def players_from_cache(cache: dict) -> List[str]:
    names = set()
    mlb = cache.get("mlb", {}) if isinstance(cache, dict) else {}

    for sec in ("batters_basic", "pitchers_basic", "batters", "pitchers"):
        block = mlb.get(sec, {}) or {}
        if isinstance(block, dict):
            for name in block.keys():
                if name:
                    names.add(str(name))

    for _, val in mlb.items():
        if isinstance(val, dict):
            for name in val.keys():
                if isinstance(name, str) and 2 <= len(name) <= 40:
                    names.add(name)

    out = sorted(names)
    cap = int(os.getenv("HISTORY_PLAYER_CAP", "220"))
    if cap > 0:
        out = out[:cap]
    return out


def mlb_search_player(name: str):
    data = http_json("https://statsapi.mlb.com/api/v1/people/search", {"names": name})
    people = (data or {}).get("people") or []
    if not people:
        return None

    n = norm_name(name)
    for p in people:
        if norm_name(p.get("fullName")) == n:
            return p
    return people[0]


def mlb_gamelog(person_id: int, group: str, season: str):
    data = http_json(
        f"https://statsapi.mlb.com/api/v1/people/{person_id}/stats",
        {
            "stats": "gameLog",
            "group": group,
            "season": season,
            "hydrate": "team",
        },
    )
    stats = (data or {}).get("stats") or []
    if not stats:
        return []
    return stats[0].get("splits") or []


def parse_mlb_split(name: str, sp: dict, season: str, pitching: bool = False) -> dict:
    st = sp.get("stat") or {}
    tm = sp.get("team") or {}
    op = sp.get("opponent") or {}
    gm = sp.get("game") or {}
    gid = str(gm.get("gamePk") or "")

    row = {
        "sport": "BASEBALL",
        "league": "MLB",
        "country": "USA",
        "season": str(season),
        "source": "mlb_statsapi",
        "source_game_id": gid,
        "game_id": gid,
        "game_date": sp.get("date"),
        "player_name": name,
        "normalized_name": norm_name(name),
        "team": tm.get("abbreviation") or tm.get("name"),
        "opponent": op.get("abbreviation") or op.get("name"),
        "home_away": str(sp.get("isHome")),
        "raw": sp,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    if pitching:
        row.update({
            "pitcher_strikeouts": to_num(st.get("strikeOuts")),
            "pitcher_innings": innings_to_float(st.get("inningsPitched")),
            "pitcher_hits_allowed": to_num(st.get("hits")),
            "pitcher_earned_runs": to_num(st.get("earnedRuns")),
            "pitcher_walks": to_num(st.get("baseOnBalls")),
            "pitcher_home_runs_allowed": to_num(st.get("homeRuns")),
            "pitcher_outs": to_num(st.get("outs")),
        })
    else:
        row.update({
            "hits": to_num(st.get("hits")),
            "total_bases": to_num(st.get("totalBases")),
            "home_runs": to_num(st.get("homeRuns")),
            "rbi": to_num(st.get("rbi")),
            "runs": to_num(st.get("runs")),
            "strikeouts_batter": to_num(st.get("strikeOuts")),
            "walks_batter": to_num(st.get("baseOnBalls")),
            "stolen_bases": to_num(st.get("stolenBases")),
        })

    return row


def fetch_mlb_history(names: List[str]) -> List[dict]:
    season = os.getenv("MLB_SEASON", os.getenv("SEASON_MLB", "2026"))
    last_n = int(os.getenv("HISTORY_LAST_N_GAMES", "30"))

    rows = []
    for idx, name in enumerate(names, start=1):
        person = mlb_search_player(name)
        if not person:
            continue

        full = person.get("fullName") or name
        pos = ((person.get("primaryPosition") or {}).get("abbreviation"))
        group = "pitching" if pos in ("P", "SP", "RP") else "hitting"

        splits = mlb_gamelog(person.get("id"), group, season)
        splits = sorted(splits, key=lambda x: x.get("date") or "", reverse=True)[:last_n]

        for sp in splits:
            row = parse_mlb_split(full, sp, season, pitching=(group == "pitching"))
            if row.get("game_id") and row.get("normalized_name"):
                rows.append(row)

        if idx % 25 == 0:
            log(f"MLB history fetched progress: players={idx}/{len(names)} rows={len(rows)}")
        time.sleep(float(os.getenv("HISTORY_FETCH_SLEEP", "0.04")))

    return rows


def main():
    log("=" * 40)
    log("PROP HUNTER V10 HISTORY SCRAPER — BATCH SAFE")
    log("=" * 40)

    cache = load_cache()
    names = players_from_cache(cache)
    log(f"players from cache: MLB={len(names)}, NBA=0, WNBA=0, NFL=0")

    if not names:
        log("history scraper done — no players")
        return

    rows = fetch_mlb_history(names)
    log(f"MLB history fetched: players={len(names)} rows={len(rows)}")

    batch_size = int(os.getenv("HISTORY_BATCH_SIZE", "75"))
    saved = batch_upsert(
        "prop_hunter_player_gamelogs",
        rows,
        "sport,league,season,game_id,normalized_name",
        batch_size,
    )

    log(f"MLB history saved: {saved}/{len(rows)}")
    log("history scraper done")


if __name__ == "__main__":
    main()
