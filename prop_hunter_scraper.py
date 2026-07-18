#!/usr/bin/env python3
"""
PROP HUNTER DATA+ SCRAPER — SAFE CACHE BUILDER
==============================================

Ziel:
- schreibt IMMER prop_hunter_data_cache.json
- füllt MLB batters_basic / pitchers_basic / team_k_rates / lineups
- füllt ESPN Scoreboards für NBA / WNBA / NFL
- optional Supabase source snapshots
- kein Telegram
- keine Picks
- kein Odds API Verbrauch

Dieses File ist bewusst leicht, damit GitHub Actions + Supabase Free nicht überlastet werden.
"""

from __future__ import annotations

import os
import json
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List

import requests

try:
    from supabase import create_client
except Exception:
    create_client = None

OUT = Path("prop_hunter_data_cache.json")
UA = "PropHunterDataPlusScraper/2.0"
TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "25"))


def log(msg: str) -> None:
    print(msg, flush=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def season_mlb() -> int:
    now = datetime.now(timezone.utc)
    return now.year if 3 <= now.month <= 11 else now.year - 1


def season_nba_label() -> str:
    now = datetime.now(timezone.utc)
    y = now.year - 1 if now.month < 10 else now.year
    return f"{y}-{str((y + 1) % 100).zfill(2)}"


def http_json(url: str, params: dict | None = None, headers: dict | None = None) -> Any:
    h = {
        "User-Agent": UA,
        "Accept": "application/json,*/*",
    }
    if headers:
        h.update(headers)
    try:
        r = requests.get(url, params=params or {}, headers=h, timeout=TIMEOUT)
        if r.status_code >= 400:
            log(f"  HTTP {r.status_code}: {url}")
            return None
        return r.json()
    except Exception as e:
        log(f"  HTTP failed {url}: {e}")
        return None


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
        log(f"  Supabase client skipped: {e}")
        return None


def upsert_snapshot(section: str, entity_key: str, payload: dict) -> None:
    sb = sb_client()
    if sb is None:
        return
    try:
        row = {
            "source_key": "prop_hunter_data_plus",
            "section": section,
            "entity_key": entity_key,
            "payload": payload,
            "updated_at": now_iso(),
        }
        sb.table("prop_hunter_source_snapshots").upsert(
            row,
            on_conflict="source_key,section,entity_key",
        ).execute()
    except Exception as e:
        log(f"  Supabase snapshot skipped {section}/{entity_key}: {e}")


def mlb_stats(group: str, fields: str, limit: int = 600) -> List[dict]:
    year = season_mlb()
    data = http_json(
        "https://statsapi.mlb.com/api/v1/stats",
        params={
            "sportId": 1,
            "season": year,
            "gameType": "R",
            "stats": "season",
            "group": group,
            "limit": limit,
            "fields": fields,
        },
    )
    if not data:
        return []
    return ((data.get("stats") or [{}])[0].get("splits") or [])


def fetch_mlb_batters() -> Dict[str, dict]:
    fields = "stats,splits,player,fullName,stat,gamesPlayed,atBats,plateAppearances,homeRuns,avg,ops,slugging,hits,totalBases,doubles,triples,rbi,runs,strikeOuts,baseOnBalls,stolenBases"
    out: Dict[str, dict] = {}
    for split in mlb_stats("hitting", fields, 700):
        player = split.get("player") or {}
        stat = split.get("stat") or {}
        name = (player.get("fullName") or "").strip()
        if not name:
            continue
        key = name.lower()
        out[key] = {
            "player_name": name,
            "source_player_id": player.get("id"),
            "games": stat.get("gamesPlayed"),
            "ab": stat.get("atBats"),
            "pa": stat.get("plateAppearances"),
            "hr": stat.get("homeRuns"),
            "hits": stat.get("hits"),
            "total_bases": stat.get("totalBases"),
            "doubles": stat.get("doubles"),
            "triples": stat.get("triples"),
            "rbi": stat.get("rbi"),
            "runs": stat.get("runs"),
            "avg": stat.get("avg"),
            "ops": stat.get("ops"),
            "slg": stat.get("slugging"),
            "strikeouts": stat.get("strikeOuts"),
            "walks": stat.get("baseOnBalls"),
            "stolen_bases": stat.get("stolenBases"),
        }
    log(f"  MLB batters basic: {len(out)}")
    return out


def fetch_mlb_pitchers() -> Dict[str, dict]:
    fields = "stats,splits,player,fullName,stat,gamesPlayed,gamesStarted,era,strikeOuts,strikeoutsPer9Inn,homeRunsPer9,whip,inningsPitched,hits,earnedRuns,baseOnBalls,wins,losses"
    out: Dict[str, dict] = {}
    for split in mlb_stats("pitching", fields, 500):
        player = split.get("player") or {}
        stat = split.get("stat") or {}
        name = (player.get("fullName") or "").strip()
        if not name:
            continue
        key = name.lower()
        out[key] = {
            "player_name": name,
            "source_player_id": player.get("id"),
            "games": stat.get("gamesPlayed"),
            "starts": stat.get("gamesStarted"),
            "era": stat.get("era"),
            "strikeouts": stat.get("strikeOuts"),
            "k9": stat.get("strikeoutsPer9Inn"),
            "hr9": stat.get("homeRunsPer9"),
            "whip": stat.get("whip"),
            "innings": stat.get("inningsPitched"),
            "hits_allowed": stat.get("hits"),
            "earned_runs": stat.get("earnedRuns"),
            "walks": stat.get("baseOnBalls"),
            "wins": stat.get("wins"),
            "losses": stat.get("losses"),
        }
    log(f"  MLB pitchers basic: {len(out)}")
    return out


def fetch_mlb_team_k_rates() -> Dict[str, dict]:
    fields = "stats,splits,team,name,stat,strikeOuts,plateAppearances"
    out: Dict[str, dict] = {}
    for split in mlb_stats("hitting", fields, 50):
        team = split.get("team") or {}
        stat = split.get("stat") or {}
        name = (team.get("name") or "").strip()
        if not name:
            continue
        so = float(stat.get("strikeOuts") or 0)
        pa = float(stat.get("plateAppearances") or 0)
        out[name.lower()] = {
            "team_name": name,
            "strikeouts": so,
            "plate_appearances": pa,
            "k_rate": round((so / pa) * 100, 2) if pa else None,
        }
    log(f"  MLB team K-rates: {len(out)}")
    return out


def fetch_mlb_lineups() -> Dict[str, dict]:
    today = datetime.now(timezone.utc).date().isoformat()
    data = http_json(
        "https://statsapi.mlb.com/api/v1/schedule",
        params={"sportId": 1, "date": today, "hydrate": "probablePitcher,team"},
    ) or {}
    out: Dict[str, dict] = {}
    games = []
    for d in data.get("dates", []) or []:
        games.extend(d.get("games", []) or [])
    for g in games:
        teams = g.get("teams") or {}
        for side in ("home", "away"):
            block = teams.get(side) or {}
            team = (block.get("team") or {}).get("name")
            pp = block.get("probablePitcher") or {}
            if team:
                out[team.lower()] = {
                    "team_name": team,
                    "probable_pitcher": pp.get("fullName"),
                    "probable_pitcher_id": pp.get("id"),
                    "game_pk": g.get("gamePk"),
                    "game_date": g.get("gameDate"),
                    "status": ((g.get("status") or {}).get("detailedState")),
                }
    log(f"  MLB lineups/probables: {len(out)} teams")
    return out


def espn_scoreboard(sport: str, league: str) -> dict:
    url = f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard"
    data = http_json(url) or {}
    events = data.get("events") or []
    log(f"  ESPN {league.upper()} scoreboard: {len(events)} events")
    return data


def main() -> int:
    log("=" * 50)
    log("PROP HUNTER DATA+ SCRAPER ONLY")
    log("No Telegram. No picks. No Odds API props.")
    log("=" * 50)

    cache: Dict[str, Any] = {
        "generated_at": now_iso(),
        "version": "data_plus_safe_cache_builder_v2",
        "mlb_season": season_mlb(),
        "nba_season": season_nba_label(),
        "mlb": {},
        "nba": {},
        "wnba": {},
        "nfl": {},
    }

    log("📦 MLB DATA+ ...")
    try:
        cache["mlb"]["team_k_rates"] = fetch_mlb_team_k_rates()
        cache["mlb"]["batters_basic"] = fetch_mlb_batters()
        cache["mlb"]["pitchers_basic"] = fetch_mlb_pitchers()
        cache["mlb"]["lineups"] = fetch_mlb_lineups()
    except Exception as e:
        log(f"  MLB DATA+ failed: {e}")

    log("📦 ESPN DATA+ ...")
    cache["nba"]["scoreboard"] = espn_scoreboard("basketball", "nba")
    time.sleep(0.2)
    cache["wnba"]["scoreboard"] = espn_scoreboard("basketball", "wnba")
    time.sleep(0.2)
    cache["nfl"]["scoreboard"] = espn_scoreboard("football", "nfl")

    OUT.write_text(json.dumps(cache, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    log(f"✅ wrote {OUT} ({OUT.stat().st_size} bytes)")

    upsert_snapshot("cache_status", "prop_hunter_data_cache", {
        "generated_at": cache["generated_at"],
        "file": str(OUT),
        "size_bytes": OUT.stat().st_size,
        "mlb_batters": len(cache["mlb"].get("batters_basic") or {}),
        "mlb_pitchers": len(cache["mlb"].get("pitchers_basic") or {}),
        "mlb_team_k": len(cache["mlb"].get("team_k_rates") or {}),
        "nba_events": len(((cache["nba"].get("scoreboard") or {}).get("events") or [])),
        "wnba_events": len(((cache["wnba"].get("scoreboard") or {}).get("events") or [])),
        "nfl_events": len(((cache["nfl"].get("scoreboard") or {}).get("events") or [])),
    })

    log("✅ DATA+ scraper done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
