#!/usr/bin/env python3
"""
PROP HUNTER — PRIZEPICKS + UNDERDOG CONNECTOR
=============================================
Keine API Keys nötig. Holt echte Linien und speichert sie in
prop_hunter_prop_snapshots (Supabase) — füllt die Datenbank mit
Statistiken/Linien, die wir sonst nicht haben.

PrizePicks ist Cloudflare-geschützt → cloudscraper, Fallback Playwright.
Underdog ist offen (JSON).
"""
from __future__ import annotations
import json, os
from typing import Any, Dict, List

from prop_hunter_shared_utils import (
    upsert_rows, safe_json_write, hash_key, now_iso, log, warn,
    norm_name, norm_market, to_float
)

OUT = "prop_hunter_pp_ud_props.json"

PP_LEAGUES = {"NBA": 7, "WNBA": 3, "MLB": 2, "NFL": 9, "NHL": 8}
UD_SPORTS = {"NBA", "WNBA", "MLB", "NFL", "NHL"}

def _pp_json(url: str):
    # 1) cloudscraper
    try:
        import cloudscraper
        s = cloudscraper.create_scraper()
        r = s.get(url, timeout=25)
        if r.status_code == 200:
            return r.json()
        warn(f"PP cloudscraper {r.status_code}")
    except Exception as e:
        warn(f"PP cloudscraper: {e}")
    # 2) Playwright Fallback
    try:
        import asyncio
        from playwright.async_api import async_playwright
        async def _go():
            async with async_playwright() as pw:
                b = await pw.chromium.launch(headless=True)
                pg = await (await b.new_context()).new_page()
                await pg.goto(url, timeout=30000)
                txt = await pg.inner_text("body")
                await b.close()
                return json.loads(txt)
        return asyncio.run(_go())
    except Exception as e:
        warn(f"PP playwright: {e}")
    return None

def fetch_prizepicks(league: str) -> List[Dict[str, Any]]:
    lid = PP_LEAGUES.get(league)
    if not lid: return []
    data = _pp_json(f"https://api.prizepicks.com/projections?league_id={lid}&per_page=500&single_stat=true")
    if not data: return []
    players = {}
    for inc in data.get("included", []) or []:
        if inc.get("type") == "new_player":
            a = inc.get("attributes", {}) or {}
            players[inc.get("id")] = {"name": a.get("display_name") or a.get("name"),
                                      "team": a.get("team")}
    rows = []
    for item in data.get("data", []) or []:
        a = item.get("attributes", {}) or {}
        rel = ((item.get("relationships", {}) or {}).get("new_player", {}) or {}).get("data", {}) or {}
        pl = players.get(rel.get("id"), {})
        name = pl.get("name"); line = to_float(a.get("line_score"))
        stat = a.get("stat_type"); 
        if not (name and line is not None and stat): continue
        rows.append({
            "snapshot_id": hash_key("prizepicks", league, name, stat, line, a.get("start_time")),
            "source": "prizepicks", "sport": league, "league": league,
            "source_sport_key": f"pp_{lid}",
            "source_event_id": str(a.get("game_id") or ""),
            "game_id": str(a.get("game_id") or ""),
            "commence_time": a.get("start_time"),
            "player_name": name, "normalized_name": norm_name(name),
            "market": stat, "market_key": norm_market(stat),
            "line": line, "odds_decimal": None,
            "bookmaker": "prizepicks",
            "home_team": None, "away_team": a.get("description"),
            "raw": a, "created_at": now_iso(),
        })
    log(f"PrizePicks {league}: {len(rows)} lines")
    return rows

def fetch_underdog() -> List[Dict[str, Any]]:
    import requests
    try:
        r = requests.get("https://api.underdogfantasy.com/beta/v3/over_under_lines",
                         timeout=25, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            warn(f"Underdog {r.status_code}"); return []
        data = r.json()
    except Exception as e:
        warn(f"Underdog: {e}"); return []
    # Appearance→Player Map
    players = {p.get("id"): p for p in data.get("players", []) or []}
    appearances = {}
    for ap in data.get("appearances", []) or []:
        pl = players.get(ap.get("player_id"), {})
        appearances[ap.get("id")] = {
            "name": f"{pl.get('first_name','')} {pl.get('last_name','')}".strip(),
            "sport": (pl.get("sport_id") or "").upper(),
            "team": ap.get("team_id"),
        }
    rows = []
    for ln in data.get("over_under_lines", []) or []:
        ou = (ln.get("over_under") or {})
        app = appearances.get(((ou.get("appearance_stat") or {}).get("appearance_id")), {})
        sport = app.get("sport", "")
        if sport not in UD_SPORTS: continue
        stat = (ou.get("appearance_stat") or {}).get("display_stat") or ""
        line = to_float(ln.get("stat_value"))
        name = app.get("name")
        if not (name and stat and line is not None): continue
        rows.append({
            "snapshot_id": hash_key("underdog", sport, name, stat, line),
            "source": "underdog", "sport": sport, "league": sport,
            "source_sport_key": "underdog",
            "source_event_id": "", "game_id": "",
            "commence_time": None,
            "player_name": name, "normalized_name": norm_name(name),
            "market": stat, "market_key": norm_market(stat),
            "line": line, "odds_decimal": None,
            "bookmaker": "underdog",
            "home_team": None, "away_team": None,
            "raw": ou, "created_at": now_iso(),
        })
    log(f"Underdog: {len(rows)} lines")
    return rows

def main():
    all_rows = []
    for lg in os.getenv("PROP_HUNTER_SPORTS", "MLB,NBA,WNBA,NFL").split(","):
        lg = lg.strip().upper()
        if lg: all_rows.extend(fetch_prizepicks(lg))
    all_rows.extend(fetch_underdog())
    safe_json_write(OUT, all_rows)
    upsert_rows("prop_hunter_prop_snapshots", all_rows, "snapshot_id")
    log(f"pp+ud done: {len(all_rows)} lines")

if __name__ == "__main__":
    main()
