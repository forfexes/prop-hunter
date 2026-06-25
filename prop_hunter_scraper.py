#!/usr/bin/env python3
"""
PROP HUNTER DATA+ SCRAPER
-------------------------
Reiner Scraper. Postet NICHT auf Telegram.
Ziel:
- Zusatzdaten sammeln
- prop_hunter_data_cache.json schreiben
- optional Supabase prop_hunter_source_snapshots befüllen

Wichtig:
Dieser Scraper verbraucht bewusst KEINE The-Odds-API-Quota.
Die Quoten holt nur prophunter.py.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import date, datetime, timezone
from typing import Any, Dict, List

import requests

try:
    import statsapi
    HAS_STATSAPI = True
except Exception:
    HAS_STATSAPI = False

try:
    from supabase import create_client
    HAS_SUPABASE = True
except Exception:
    HAS_SUPABASE = False


SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
CACHE_FILE = "prop_hunter_data_cache.json"
TIMEOUT = 25

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("prop_hunter_scraper")


def season_mlb() -> int:
    now = datetime.now(timezone.utc)
    return now.year if 3 <= now.month <= 11 else now.year - 1


def safe_get_json(url: str, params: Dict[str, Any] | None = None, timeout: int = TIMEOUT) -> Dict[str, Any]:
    try:
        r = requests.get(
            url,
            params=params or {},
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 PropHunterDataPlus/1.0"},
        )
        if r.status_code != 200:
            log.warning("GET %s -> %s", url, r.status_code)
            return {}
        return r.json()
    except Exception as e:
        log.warning("GET failed %s: %s", url, e)
        return {}


def fetch_mlb_schedule() -> List[Dict[str, Any]]:
    if not HAS_STATSAPI:
        log.warning("statsapi not installed")
        return []

    today = date.today().isoformat()
    out: List[Dict[str, Any]] = []

    try:
        games = statsapi.schedule(date=today)
        for g in games:
            out.append(
                {
                    "game_id": g.get("game_id"),
                    "date": g.get("game_date") or today,
                    "home": g.get("home_name"),
                    "away": g.get("away_name"),
                    "home_probable_pitcher": g.get("home_probable_pitcher"),
                    "away_probable_pitcher": g.get("away_probable_pitcher"),
                    "status": g.get("status"),
                    "venue": g.get("venue_name"),
                    "source": "mlb_statsapi_schedule",
                }
            )
    except Exception as e:
        log.warning("MLB schedule failed: %s", e)

    log.info("MLB schedule: %d games", len(out))
    return out


def fetch_mlb_team_k_rates() -> Dict[str, Any]:
    year = season_mlb()
    data = safe_get_json(
        "https://statsapi.mlb.com/api/v1/stats",
        {
            "sportId": 1,
            "season": year,
            "gameType": "R",
            "stats": "season",
            "group": "hitting",
            "limit": 30,
            "fields": "stats,splits,team,name,stat,strikeOuts,plateAppearances",
        },
    )

    out: Dict[str, Any] = {}
    splits = (((data.get("stats") or [{}])[0]).get("splits") or [])
    for split in splits:
        team = ((split.get("team") or {}).get("name") or "").strip()
        stat = split.get("stat") or {}
        if not team:
            continue
        so = int(stat.get("strikeOuts") or 0)
        pa = int(stat.get("plateAppearances") or 0)
        out[team.lower()] = {
            "team": team,
            "strikeouts": so,
            "plate_appearances": pa,
            "k_rate": round((so / pa) * 100, 2) if pa else None,
            "season": year,
            "source": "mlb_statsapi_team_k_rates",
        }

    log.info("MLB team K-rates: %d teams", len(out))
    return out


def fetch_mlb_batter_basic() -> Dict[str, Any]:
    year = season_mlb()
    data = safe_get_json(
        "https://statsapi.mlb.com/api/v1/stats",
        {
            "sportId": 1,
            "season": year,
            "gameType": "R",
            "stats": "season",
            "group": "hitting",
            "limit": 500,
            "fields": "stats,splits,player,fullName,team,name,stat,homeRuns,hits,avg,ops,slugging,atBats",
        },
    )

    out: Dict[str, Any] = {}
    splits = (((data.get("stats") or [{}])[0]).get("splits") or [])
    for split in splits:
        player = ((split.get("player") or {}).get("fullName") or "").strip()
        team = ((split.get("team") or {}).get("name") or "").strip()
        stat = split.get("stat") or {}
        if not player:
            continue
        out[player.lower()] = {
            "player": player,
            "team": team,
            "hr": int(stat.get("homeRuns") or 0),
            "hits": int(stat.get("hits") or 0),
            "ab": int(stat.get("atBats") or 0),
            "avg": stat.get("avg"),
            "ops": stat.get("ops"),
            "slg": stat.get("slugging"),
            "season": year,
            "source": "mlb_statsapi_batter_basic",
        }

    log.info("MLB batters basic: %d players", len(out))
    return out


def fetch_mlb_pitcher_basic() -> Dict[str, Any]:
    year = season_mlb()
    data = safe_get_json(
        "https://statsapi.mlb.com/api/v1/stats",
        {
            "sportId": 1,
            "season": year,
            "gameType": "R",
            "stats": "season",
            "group": "pitching",
            "limit": 500,
            "fields": "stats,splits,player,fullName,team,name,stat,era,strikeoutsPer9Inn,homeRunsPer9,whip",
        },
    )

    out: Dict[str, Any] = {}
    splits = (((data.get("stats") or [{}])[0]).get("splits") or [])
    for split in splits:
        player = ((split.get("player") or {}).get("fullName") or "").strip()
        team = ((split.get("team") or {}).get("name") or "").strip()
        stat = split.get("stat") or {}
        if not player:
            continue
        out[player.lower()] = {
            "player": player,
            "team": team,
            "era": stat.get("era"),
            "k9": stat.get("strikeoutsPer9Inn"),
            "hr9": stat.get("homeRunsPer9"),
            "whip": stat.get("whip"),
            "season": year,
            "source": "mlb_statsapi_pitcher_basic",
        }

    log.info("MLB pitchers basic: %d players", len(out))
    return out


def fetch_espn_scoreboard(sport: str) -> Dict[str, Any]:
    # sport: nba, wnba, nfl
    league_map = {
        "nba": ("basketball", "nba"),
        "wnba": ("basketball", "wnba"),
        "nfl": ("football", "nfl"),
    }
    if sport not in league_map:
        return {}

    group, league = league_map[sport]
    url = f"https://site.api.espn.com/apis/site/v2/sports/{group}/{league}/scoreboard"
    data = safe_get_json(url, {"dates": date.today().strftime("%Y%m%d")})
    events = data.get("events") or []
    out = {
        "sport": sport.upper(),
        "date": date.today().isoformat(),
        "events": events,
        "source": f"espn_{sport}_scoreboard",
    }
    log.info("ESPN %s scoreboard: %d events", sport.upper(), len(events))
    return out


def write_cache(payload: Dict[str, Any]) -> None:
    Path(CACHE_FILE).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("wrote %s", CACHE_FILE)


def supabase_upsert_snapshot(source_key: str, section: str, entity_key: str, payload: Any) -> None:
    if not (HAS_SUPABASE and SUPABASE_URL and SUPABASE_KEY):
        return

    try:
        sb = create_client(SUPABASE_URL, SUPABASE_KEY)
        row = {
            "source_key": source_key,
            "section": section,
            "entity_key": entity_key,
            "payload": payload,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        # on_conflict needs a unique constraint on source_key, section, entity_key.
        # If that constraint does not exist, fallback to insert.
        try:
            sb.table("prop_hunter_source_snapshots").upsert(
                row,
                on_conflict="source_key,section,entity_key",
            ).execute()
        except Exception:
            sb.table("prop_hunter_source_snapshots").insert(row).execute()
    except Exception as e:
        log.warning("Supabase snapshot failed %s/%s/%s: %s", source_key, section, entity_key, e)


def main() -> None:
    started = time.time()
    log.info("========================================")
    log.info("PROP HUNTER DATA+ SCRAPER ONLY")
    log.info("No Telegram. No picks. No Odds API props.")
    log.info("========================================")

    payload: Dict[str, Any] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mlb": {
            "schedule": fetch_mlb_schedule(),
            "team_k_rates": fetch_mlb_team_k_rates(),
            "batters_basic": fetch_mlb_batter_basic(),
            "pitchers_basic": fetch_mlb_pitcher_basic(),
        },
        "nba": {
            "scoreboard": fetch_espn_scoreboard("nba"),
        },
        "wnba": {
            "scoreboard": fetch_espn_scoreboard("wnba"),
        },
        "nfl": {
            "scoreboard": fetch_espn_scoreboard("nfl"),
        },
    }

    write_cache(payload)

    # Supabase snapshots, alles mit prop_hunter_ Tabelle.
    supabase_upsert_snapshot("mlb_statsapi", "schedule", date.today().isoformat(), payload["mlb"]["schedule"])
    supabase_upsert_snapshot("mlb_statsapi", "team_k_rates", str(season_mlb()), payload["mlb"]["team_k_rates"])
    supabase_upsert_snapshot("mlb_statsapi", "batters_basic", str(season_mlb()), payload["mlb"]["batters_basic"])
    supabase_upsert_snapshot("mlb_statsapi", "pitchers_basic", str(season_mlb()), payload["mlb"]["pitchers_basic"])
    supabase_upsert_snapshot("espn", "nba_scoreboard", date.today().isoformat(), payload["nba"]["scoreboard"])
    supabase_upsert_snapshot("espn", "wnba_scoreboard", date.today().isoformat(), payload["wnba"]["scoreboard"])
    supabase_upsert_snapshot("espn", "nfl_scoreboard", date.today().isoformat(), payload["nfl"]["scoreboard"])

    log.info("DATA+ scraper done in %.1fs", time.time() - started)


if __name__ == "__main__":
    main()
