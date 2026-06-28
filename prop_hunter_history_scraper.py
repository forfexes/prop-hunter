#!/usr/bin/env python3
"""
PROP HUNTER V10 — HISTORY SCRAPER

Phase 1:
- MLB Last 30 über MLB StatsAPI
- speichert in prop_hunter_player_gamelogs
- vorbereitet für NBA/WNBA/NFL/KBO/NPB usw.
"""

from __future__ import annotations
import os, re, json, time, hashlib
from pathlib import Path
from datetime import datetime
from typing import Any
import requests

try:
    from supabase import create_client
except Exception:
    create_client = None

CACHE_FILE = Path("prop_hunter_data_cache.json")
TIMEOUT = 20

def log(x): print(datetime.now().strftime("%H:%M:%S"), "INFO   ", x, flush=True)
def warn(x): print(datetime.now().strftime("%H:%M:%S"), "WARNING", x, flush=True)

def norm_name(s: Any) -> str:
    s = str(s or "").lower().strip()
    s = re.sub(r"[^a-z0-9\s\.\-']", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def to_num(x):
    try:
        if x is None or x == "":
            return None
        return float(x)
    except Exception:
        return None

def innings_to_float(x):
    try:
        s = str(x)
        if "." not in s:
            return float(s)
        a, b = s.split(".", 1)
        return float(a) + float(b) / 3.0
    except Exception:
        return None

def sb():
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

def upsert(table, rows, conflict=None):
    if not rows:
        return
    c = sb()
    if c is None:
        warn(f"Supabase missing; skipped {table}")
        return
    try:
        q = c.table(table).upsert(rows, on_conflict=conflict) if conflict else c.table(table).insert(rows)
        q.execute()
        log(f"{table}: saved {len(rows)} rows")
    except Exception as e:
        warn(f"{table} save failed: {e}")

def http_json(url, params=None):
    try:
        r = requests.get(url, params=params or {}, timeout=TIMEOUT, headers={"User-Agent": "PropHunter/10"})
        if r.status_code >= 400:
            warn(f"HTTP {r.status_code}: {url}")
            return None
        return r.json()
    except Exception as e:
        warn(f"HTTP failed: {e}")
        return None

def load_cache():
    if not CACHE_FILE.exists():
        return {}
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def players_from_cache(cache):
    players = {"MLB": set(), "NBA": set(), "WNBA": set(), "NFL": set()}
    mlb = cache.get("mlb", {}) if isinstance(cache, dict) else {}
    for sec in ("batters_basic", "pitchers_basic"):
        m = mlb.get(sec, {}) or {}
        if isinstance(m, dict):
            for n in m.keys():
                if n:
                    players["MLB"].add(str(n))
    return players

def mlb_search_player(name):
    data = http_json("https://statsapi.mlb.com/api/v1/people/search", {"names": name})
    people = (data or {}).get("people") or []
    if not people:
        return None
    nn = norm_name(name)
    for p in people:
        if norm_name(p.get("fullName")) == nn:
            return p
    return people[0]

def mlb_gamelog(pid, group, season):
    data = http_json(
        f"https://statsapi.mlb.com/api/v1/people/{pid}/stats",
        {"stats": "gameLog", "group": group, "season": season, "hydrate": "team"},
    )
    stats = (data or {}).get("stats") or []
    if not stats:
        return []
    return stats[0].get("splits") or []

def parse_hitting(name, sp, season):
    st, tm, op, gm = sp.get("stat") or {}, sp.get("team") or {}, sp.get("opponent") or {}, sp.get("game") or {}
    gid = str(gm.get("gamePk") or hashlib.md5(json.dumps(sp, sort_keys=True).encode()).hexdigest()[:16])
    return {
        "sport": "BASEBALL", "league": "MLB", "country": "USA", "season": season, "source": "mlb_statsapi",
        "source_game_id": gid, "game_id": gid, "game_date": sp.get("date"),
        "player_name": name, "normalized_name": norm_name(name),
        "team": tm.get("abbreviation") or tm.get("name"), "opponent": op.get("abbreviation") or op.get("name"),
        "home_away": str(sp.get("isHome")),
        "hits": to_num(st.get("hits")), "total_bases": to_num(st.get("totalBases")),
        "home_runs": to_num(st.get("homeRuns")), "rbi": to_num(st.get("rbi")),
        "runs": to_num(st.get("runs")), "strikeouts_batter": to_num(st.get("strikeOuts")),
        "walks_batter": to_num(st.get("baseOnBalls")),
        "raw": sp,
    }

def parse_pitching(name, sp, season):
    st, tm, op, gm = sp.get("stat") or {}, sp.get("team") or {}, sp.get("opponent") or {}, sp.get("game") or {}
    gid = str(gm.get("gamePk") or hashlib.md5(json.dumps(sp, sort_keys=True).encode()).hexdigest()[:16])
    return {
        "sport": "BASEBALL", "league": "MLB", "country": "USA", "season": season, "source": "mlb_statsapi",
        "source_game_id": gid, "game_id": gid, "game_date": sp.get("date"),
        "player_name": name, "normalized_name": norm_name(name),
        "team": tm.get("abbreviation") or tm.get("name"), "opponent": op.get("abbreviation") or op.get("name"),
        "home_away": str(sp.get("isHome")),
        "pitcher_strikeouts": to_num(st.get("strikeOuts")),
        "pitcher_innings": innings_to_float(st.get("inningsPitched")),
        "pitcher_hits_allowed": to_num(st.get("hits")),
        "pitcher_earned_runs": to_num(st.get("earnedRuns")),
        "pitcher_walks": to_num(st.get("baseOnBalls")),
        "pitcher_home_runs_allowed": to_num(st.get("homeRuns")),
        "raw": sp,
    }

def fetch_mlb_history(names, last_n=30):
    rows = []
    season = os.getenv("MLB_SEASON") or str(datetime.now().year)
    for i, nm in enumerate(sorted(names)):
        if i >= 250:
            warn("runtime cap 250 MLB players")
            break
        person = mlb_search_player(nm)
        if not person:
            continue
        full = person.get("fullName") or nm
        pos = ((person.get("primaryPosition") or {}).get("abbreviation"))
        group = "pitching" if pos in ("P", "SP", "RP") else "hitting"
        splits = sorted(mlb_gamelog(person.get("id"), group, season), key=lambda x: x.get("date") or "", reverse=True)[:last_n]
        for sp in splits:
            rows.append(parse_pitching(full, sp, season) if group == "pitching" else parse_hitting(full, sp, season))
        time.sleep(0.05)
    upsert("prop_hunter_player_gamelogs", rows, "sport,league,season,game_id,normalized_name")
    log(f"MLB history fetched: players={len(names)} rows={len(rows)}")

def main():
    log("=" * 40)
    log("PROP HUNTER V10 HISTORY SCRAPER")
    log("=" * 40)
    cache = load_cache()
    players = players_from_cache(cache)
    log("players from cache: " + ", ".join(f"{k}={len(v)}" for k, v in players.items()))
    if players["MLB"]:
        fetch_mlb_history(players["MLB"], int(os.getenv("LAST_N_GAMES", "30")))
    log("history scraper done")

if __name__ == "__main__":
    main()
