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

def fetch_sleeper() -> List[Dict[str, Any]]:
    import requests
    rows = []
    try:
        r = requests.get("https://api.sleeper.app/lines/available",
                         timeout=25, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            warn(f"Sleeper {r.status_code}"); return []
        data = r.json()
        items = data if isinstance(data, list) else data.get("lines", []) or data.get("data", []) or []
        for it in items:
            sport = str(it.get("sport") or "").upper()
            if sport not in ("NBA","WNBA","MLB","NFL","NHL"): continue
            name = it.get("subject") or it.get("player_name") or (it.get("subject_info") or {}).get("name")
            stat = it.get("wager_type") or it.get("stat") or it.get("market")
            line = to_float((it.get("options") or [{}])[0].get("outcome_value") if it.get("options") else it.get("line"))
            if not (name and stat and line is not None): continue
            rows.append({
                "snapshot_id": hash_key("sleeper", sport, name, stat, line),
                "source": "sleeper", "sport": sport, "league": sport,
                "source_sport_key": "sleeper",
                "source_event_id": str(it.get("game_id") or ""), "game_id": str(it.get("game_id") or ""),
                "commence_time": None,
                "player_name": name, "normalized_name": norm_name(name),
                "market": stat, "market_key": norm_market(stat),
                "line": line, "odds_decimal": None, "bookmaker": "sleeper",
                "home_team": None, "away_team": None,
                "raw": it, "created_at": now_iso(),
            })
        log(f"Sleeper: {len(rows)} lines")
    except Exception as e:
        warn(f"Sleeper: {e}")
    return rows

# ─────────────────────────────────────────────
# DRAFTKINGS SPORTSBOOK (öffentliches JSON, echte Odds!)
# ─────────────────────────────────────────────
DK_GROUPS = {"MLB": 84240, "NBA": 42648, "NFL": 88808, "NHL": 42133, "WNBA": 94682}

def fetch_draftkings(league: str) -> List[Dict[str, Any]]:
    import requests
    gid = DK_GROUPS.get(league)
    if not gid: return []
    rows = []
    try:
        r = requests.get(
            f"https://sportsbook.draftkings.com/sites/US-SB/api/v5/eventgroups/{gid}?format=json",
            timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            warn(f"DK {league}: {r.status_code}"); return []
        eg = (r.json() or {}).get("eventGroup", {}) or {}
        events = {str(e.get("eventId")): e for e in eg.get("events", []) or []}
        for cat in eg.get("offerCategories", []) or []:
            for sub in cat.get("offerSubcategoryDescriptors", []) or []:
                osc = (sub.get("offerSubcategory") or {})
                for offer_list in osc.get("offers", []) or []:
                    for offer in offer_list or []:
                        label = offer.get("label") or ""
                        ev = events.get(str(offer.get("eventId")), {})
                        for oc in offer.get("outcomes", []) or []:
                            participant = oc.get("participant") or oc.get("playerNameIdentifier")
                            line = to_float(oc.get("line"))
                            dec = to_float(oc.get("oddsDecimal"))
                            if not (participant and line is not None and dec): continue
                            side = "under" if "under" in str(oc.get("label","")).lower() else "over"
                            rows.append({
                                "snapshot_id": hash_key("draftkings", league, participant, label, line, side),
                                "source": "draftkings", "sport": league, "league": league,
                                "source_sport_key": f"dk_{gid}",
                                "source_event_id": str(offer.get("eventId") or ""),
                                "game_id": str(offer.get("eventId") or ""),
                                "commence_time": ev.get("startDate"),
                                "player_name": participant, "normalized_name": norm_name(participant),
                                "market": f"{label} {side}", "market_key": norm_market(label),
                                "line": line, "odds_decimal": dec, "bookmaker": "draftkings",
                                "home_team": (ev.get("team2") or {}).get("name") if isinstance(ev.get("team2"), dict) else ev.get("teamName2"),
                                "away_team": (ev.get("team1") or {}).get("name") if isinstance(ev.get("team1"), dict) else ev.get("teamName1"),
                                "raw": {"offer": label, "outcome": oc.get("label")}, "created_at": now_iso(),
                            })
        log(f"DraftKings {league}: {len(rows)} outcomes")
    except Exception as e:
        warn(f"DK {league}: {e}")
    return rows


# ═════════════════════════════════════════════
# ZUSÄTZLICHE ÖFFENTLICHE ODDS-QUELLEN (Fallback-Kette)
# ═════════════════════════════════════════════

def fetch_fanduel(league: str) -> List[Dict[str, Any]]:
    """FanDuel Sportsbook öffentliche API (echte Odds)."""
    import requests
    FD_EVENTGROUP = {"MLB": "mlb", "NBA": "nba", "WNBA": "wnba", "NFL": "nfl", "NHL": "nhl"}
    slug = FD_EVENTGROUP.get(league)
    if not slug: return []
    rows = []
    try:
        # FanDuel Sportsbook API (Sportsbook.fanduel.com)
        url = f"https://sbapi.nj.sportsbook.fanduel.com/api/content-managed-page"
        r = requests.get(url, params={"page": "CUSTOM", "customPageId": slug,
            "_ak": "FhMFpcPWXMeyZxOx", "timezone": "America/New_York"},
            timeout=25, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            warn(f"FanDuel {league}: {r.status_code}"); return []
        data = r.json()
        markets = (data.get("attachments", {}) or {}).get("markets", {}) or {}
        events = (data.get("attachments", {}) or {}).get("events", {}) or {}
        for mid, mk in markets.items():
            mname = (mk.get("marketName") or "").lower()
            if not any(k in mname for k in ("player","batter","pitcher","points","rebounds","assists","home run","hits","bases","strikeout")):
                continue
            ev = events.get(str(mk.get("eventId")), {})
            for rr in mk.get("runners", []) or []:
                player = rr.get("runnerName")
                price = ((rr.get("winRunnerOdds") or {}).get("decimalOdds") or {}).get("decimalOdds")
                handicap = rr.get("handicap")
                if not (player and price): continue
                rows.append({
                    "snapshot_id": hash_key("fanduel", league, player, mname, handicap),
                    "source": "fanduel", "sport": league, "league": league,
                    "source_sport_key": "fanduel", "source_event_id": str(mk.get("eventId") or ""),
                    "game_id": str(mk.get("eventId") or ""), "commence_time": ev.get("openDate"),
                    "player_name": player, "normalized_name": norm_name(player),
                    "market": mk.get("marketName") or mname, "market_key": norm_market(mname),
                    "line": to_float(handicap), "odds_decimal": to_float(price),
                    "bookmaker": "fanduel", "home_team": None, "away_team": ev.get("name"),
                    "raw": {}, "created_at": now_iso(),
                })
        log(f"FanDuel {league}: {len(rows)} outcomes")
    except Exception as e:
        warn(f"FanDuel {league}: {e}")
    return rows

def fetch_bovada(league: str) -> List[Dict[str, Any]]:
    """Bovada öffentliche API (kein Key, sehr zuverlässig für Props)."""
    import requests
    BOVADA_PATH = {
        "MLB": "baseball/mlb", "NBA": "basketball/nba", "WNBA": "basketball/wnba",
        "NFL": "football/nfl", "NHL": "hockey/nhl",
    }
    path = BOVADA_PATH.get(league)
    if not path: return []
    rows = []
    try:
        url = f"https://www.bovada.lv/services/sports/event/coupon/events/A/description/{path}"
        r = requests.get(url, params={"marketFilterId": "def", "preMatchOnly": "true",
            "lang": "en"}, timeout=25, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            warn(f"Bovada {league}: {r.status_code}"); return []
        data = r.json()
        for grp in data:
            for ev in grp.get("events", []) or []:
                ev_desc = ev.get("description", "")
                for dg in ev.get("displayGroups", []) or []:
                    for mk in dg.get("markets", []) or []:
                        mdesc = (mk.get("description") or "").lower()
                        if not any(k in mdesc for k in ("player","batter","pitcher","points","rebounds","assists","home run","hits","total bases","strikeout")):
                            continue
                        for oc in mk.get("outcomes", []) or []:
                            player = oc.get("description")
                            price = ((oc.get("price") or {}).get("decimal"))
                            handicap = (oc.get("price") or {}).get("handicap")
                            if not (player and price): continue
                            rows.append({
                                "snapshot_id": hash_key("bovada", league, player, mdesc, handicap),
                                "source": "bovada", "sport": league, "league": league,
                                "source_sport_key": "bovada", "source_event_id": str(ev.get("id") or ""),
                                "game_id": str(ev.get("id") or ""), "commence_time": None,
                                "player_name": player, "normalized_name": norm_name(player),
                                "market": mk.get("description") or mdesc, "market_key": norm_market(mdesc),
                                "line": to_float(handicap), "odds_decimal": to_float(price),
                                "bookmaker": "bovada", "home_team": None, "away_team": ev_desc,
                                "raw": {}, "created_at": now_iso(),
                            })
        log(f"Bovada {league}: {len(rows)} outcomes")
    except Exception as e:
        warn(f"Bovada {league}: {e}")
    return rows

def fetch_espn_bet(league: str) -> List[Dict[str, Any]]:
    """ESPN BET / ESPN odds öffentliche API."""
    import requests
    ESPN_PATH = {
        "MLB": "baseball/mlb", "NBA": "basketball/nba", "WNBA": "basketball/wnba",
        "NFL": "football/nfl", "NHL": "hockey/nhl",
    }
    path = ESPN_PATH.get(league)
    if not path: return []
    rows = []
    try:
        # ESPN scoreboard → events, dann odds pro event
        sb = requests.get(f"https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard",
            timeout=25, headers={"User-Agent": "Mozilla/5.0"})
        if sb.status_code != 200: return []
        for ev in sb.json().get("events", [])[:15]:
            eid = ev.get("id")
            if not eid: continue
            # ESPN Core API für Player Props
            try:
                pr = requests.get(
                    f"https://sports.core.api.espn.com/v2/sports/{path}/events/{eid}/competitions/{eid}/odds",
                    timeout=15, headers={"User-Agent": "Mozilla/5.0"})
                if pr.status_code != 200: continue
                # ESPN liefert meist Spielwetten, Props begrenzt — nehmen was da ist
            except Exception:
                continue
        # ESPN ist primär für Scores; Props limitiert. Soft return.
        if rows: log(f"ESPN BET {league}: {len(rows)} outcomes")
    except Exception as e:
        warn(f"ESPN BET {league}: {e}")
    return rows


def main():
    all_rows = []
    sports = [s.strip().upper() for s in os.getenv("PROP_HUNTER_SPORTS", "MLB,NBA,WNBA,NFL").split(",") if s.strip()]

    # Quellen-Kette pro Sport: jede in try, keine blockiert die andere.
    # Odds-Quellen (echte Quoten): Bovada, FanDuel, DraftKings
    # Linien-Quellen (synthetische Odds via DB): PrizePicks, Underdog, Sleeper
    per_sport_sources = [
        ("Bovada", fetch_bovada),
        ("DraftKings", fetch_draftkings),
        ("FanDuel", fetch_fanduel),
        ("PrizePicks", fetch_prizepicks),
    ]
    global_sources = [
        ("Underdog", fetch_underdog),
        ("Sleeper", fetch_sleeper),
    ]

    for lg in sports:
        for name, fn in per_sport_sources:
            try:
                rows = fn(lg)
                if rows:
                    all_rows.extend(rows)
            except Exception as e:
                warn(f"{name} {lg}: {e}")

    for name, fn in global_sources:
        try:
            rows = fn()
            if rows:
                all_rows.extend(rows)
        except Exception as e:
            warn(f"{name}: {e}")

    # Dedupe: pro (Spieler|Markt|Linie) die BESTE (höchste) echte Quote behalten.
    best = {}
    for r in all_rows:
        key = f"{r.get('normalized_name')}|{r.get('market_key')}|{r.get('line')}"
        od = r.get("odds_decimal")
        cur = best.get(key)
        if cur is None:
            best[key] = r
        else:
            # bevorzuge Eintrag mit echter Odds > synthetisch/None
            cur_od = cur.get("odds_decimal")
            if od is not None and (cur_od is None or od > cur_od):
                best[key] = r
    uniq = list(best.values())

    safe_json_write(OUT, uniq)
    if uniq:
        try:
            upsert_rows("prop_hunter_prop_snapshots", uniq, "snapshot_id")
        except Exception as e:
            warn(f"snapshot upsert: {e}")

    # Quellen-Statistik loggen
    by_src = {}
    for r in uniq:
        s = r.get("source", "?")
        by_src[s] = by_src.get(s, 0) + 1
    log(f"ALL SOURCES done: {len(uniq)} unique lines | " + ", ".join(f"{k}:{v}" for k,v in sorted(by_src.items())))

if __name__ == "__main__":
    main()
