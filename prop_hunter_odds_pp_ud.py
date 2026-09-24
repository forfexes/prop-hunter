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
    norm_name, norm_market, to_float, american_to_decimal
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
    # 2) curl_cffi: public endpoint with a real Chrome TLS/browser fingerprint
    try:
        from prop_hunter_http import get
        r = get(url, timeout=25, allow_curl_fallback=True)
        if r.status_code == 200:
            return r.json()
        warn(f"PP curl_cffi/http {r.status_code}")
    except Exception as e:
        warn(f"PP curl_cffi/http: {e}")
    # 3) Playwright fallback is maintenance-only. Normal card runs explicitly
    # disable browsers; do not even import/launch Playwright in that mode.
    browser_enabled = str(os.getenv("PH_BROWSER_ENABLED", "0")).lower() in {"1", "true", "yes", "on"}
    if browser_enabled:
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


def _parse_underdog_payload(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalize the public Underdog payload without inventing sportsbook odds.

    Underdog exposes one projection with two priced choices.  We keep the projection
    as one row, preserve both Higher/Lower prices as evidence, and join player,
    appearance and game records so scheduled cards retain the kickoff time.
    """
    if not isinstance(data, dict):
        return []

    players = {str(x.get("id")): x for x in (data.get("players") or []) if isinstance(x, dict)}
    games = {}
    for key in ("games", "solo_games"):
        for game in data.get(key, []) or []:
            if isinstance(game, dict) and game.get("id") is not None:
                games[str(game.get("id"))] = game

    appearances = {}
    for ap in data.get("appearances", []) or []:
        if not isinstance(ap, dict) or ap.get("id") is None:
            continue
        player = players.get(str(ap.get("player_id")), {})
        game = games.get(str(ap.get("match_id")), {})
        sport = str(player.get("sport_id") or game.get("sport_id") or "").upper().strip()
        appearances[str(ap.get("id"))] = {
            "appearance": ap,
            "player": player,
            "game": game,
            "sport": sport,
            "name": str(
                player.get("display_name") or player.get("name") or
                f"{player.get('first_name', '')} {player.get('last_name', '')}".strip()
            ).strip(),
        }

    def _choice(options, wanted):
        for option in options or []:
            if str((option or {}).get("choice") or "").lower() == wanted:
                return option or {}
        return {}

    def _split_matchup(title: str):
        title = str(title or "").strip()
        for sep in (" @ ", " vs ", " v "):
            if sep in title:
                left, right = title.split(sep, 1)
                # Underdog's standard title is AWAY @ HOME.
                return left.strip(), right.strip()
        return "", ""

    rows: List[Dict[str, Any]] = []
    for line_obj in data.get("over_under_lines", []) or []:
        if not isinstance(line_obj, dict):
            continue
        status = str(line_obj.get("status") or "active").lower()
        is_live = bool(line_obj.get("live_event"))
        if status in {"suspended", "closed", "settled", "cancelled", "canceled"} or is_live:
            continue

        over_under = line_obj.get("over_under") or {}
        appearance_stat = over_under.get("appearance_stat") or {}
        ctx = appearances.get(str(appearance_stat.get("appearance_id")), {})
        sport = str(ctx.get("sport") or "").upper()
        if sport not in UD_SPORTS:
            continue

        player = ctx.get("player") or {}
        appearance = ctx.get("appearance") or {}
        game = ctx.get("game") or {}
        name = str(ctx.get("name") or "").strip()
        machine_stat = str(appearance_stat.get("stat") or "").strip()
        display_stat = str(appearance_stat.get("display_stat") or machine_stat).strip()
        stat_value = to_float(line_obj.get("stat_value"))
        if not (name and display_stat and stat_value is not None):
            continue

        options = line_obj.get("options") or []
        higher = _choice(options, "higher")
        lower = _choice(options, "lower")
        higher_dec = to_float(higher.get("decimal_price")) or american_to_decimal(higher.get("american_price"))
        lower_dec = to_float(lower.get("decimal_price")) or american_to_decimal(lower.get("american_price"))
        game_id = str(appearance.get("match_id") or game.get("id") or "")
        game_title = str(game.get("full_team_names_title") or game.get("title") or "").strip()
        away_team, home_team = _split_matchup(game_title)
        scheduled_at = game.get("scheduled_at") or game.get("starts_at") or game.get("start_time")
        price_type = "pickem_priced" if higher_dec and lower_dec else "fantasy_fixed"

        raw_context = {
            "line_id": line_obj.get("id"),
            "line_type": line_obj.get("line_type"),
            "status": status,
            "stat_value": line_obj.get("stat_value"),
            "over_under": over_under,
            "appearance_stat": appearance_stat,
            "options": options,
            "appearance": {
                "id": appearance.get("id"), "match_id": appearance.get("match_id"),
                "match_type": appearance.get("match_type"), "player_id": appearance.get("player_id"),
                "team_id": appearance.get("team_id"),
            },
            "game": {
                "id": game.get("id"), "title": game.get("title"),
                "full_team_names_title": game.get("full_team_names_title"),
                "scheduled_at": scheduled_at, "status": game.get("status"),
            },
            "player": {
                "id": player.get("id"), "first_name": player.get("first_name"),
                "last_name": player.get("last_name"), "position_name": player.get("position_name"),
                "sport_id": player.get("sport_id"), "team_id": player.get("team_id"),
            },
        }
        rows.append({
            "snapshot_id": hash_key("underdog", sport, game_id, name, machine_stat or display_stat, stat_value),
            "source": "underdog", "sport": sport, "league": sport,
            "source_sport_key": f"underdog_{sport.lower()}",
            "source_event_id": game_id, "game_id": game_id,
            "commence_time": scheduled_at,
            "player_name": name, "normalized_name": norm_name(name),
            "team": appearance.get("team_id") or player.get("team_id"),
            "position": player.get("position_name"),
            "market": display_stat, "market_original": display_stat,
            "market_key": norm_market(machine_stat or display_stat),
            "line": stat_value, "odds_decimal": None,
            "higher_odds_decimal": higher_dec,
            "lower_odds_decimal": lower_dec,
            "higher_american": higher.get("american_price"),
            "lower_american": lower.get("american_price"),
            "higher_payout_multiplier": to_float(higher.get("payout_multiplier")),
            "lower_payout_multiplier": to_float(lower.get("payout_multiplier")),
            "bookmaker": "underdog", "price_type": price_type,
            "source_payload_observed": True,
            "home_team": home_team or None, "away_team": away_team or None,
            "game_title": game_title or None,
            "is_live": False, "card_eligible": True,
            "settlement_supported": True,
            "raw": raw_context, "created_at": now_iso(),
        })
    return rows


def fetch_underdog() -> List[Dict[str, Any]]:
    import requests
    try:
        r = requests.get(
            "https://api.underdogfantasy.com/beta/v3/over_under_lines",
            timeout=25,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
        )
        if r.status_code != 200:
            warn(f"Underdog {r.status_code}")
            return []
        rows = _parse_underdog_payload(r.json())
    except Exception as e:
        warn(f"Underdog: {e}")
        return []

    mix: Dict[str, int] = {}
    for row in rows:
        key = f"{row.get('sport')}:{row.get('market_key')}"
        mix[key] = mix.get(key, 0) + 1
    preview = ", ".join(f"{k}={v}" for k, v in sorted(mix.items(), key=lambda kv: (-kv[1], kv[0]))[:8])
    log(f"Underdog: {len(rows)} lines" + (f" | {preview}" if preview else ""))
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



_SNAPSHOT_DB_FIELDS = {
    "snapshot_id", "source", "bookmaker", "sport", "league",
    "source_event_id", "event_id", "game_id", "player_name", "normalized_name",
    "market", "market_key", "direction", "line", "odds", "odds_decimal",
    "period", "is_live", "commence_time", "raw", "created_at", "updated_at",
}

def _snapshot_db_rows(rows):
    """Project rich source rows onto the stable Supabase snapshot schema.

    Extra source fields (game_title, position, payout sides, observed flags, etc.)
    are retained inside raw JSON instead of being sent as unknown columns.
    """
    out = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        db = {k: v for k, v in row.items() if k in _SNAPSHOT_DB_FIELDS}
        raw = dict(row.get("raw") or {}) if isinstance(row.get("raw"), dict) else {"raw": row.get("raw")}
        extras = {k: v for k, v in row.items() if k not in _SNAPSHOT_DB_FIELDS and v is not None}
        if extras:
            raw["source_extras"] = extras
        db["raw"] = raw
        # Keep both legacy `odds` and canonical `odds_decimal` coherent.
        if db.get("odds_decimal") is None and row.get("decimal_odds") is not None:
            db["odds_decimal"] = row.get("decimal_odds")
        if db.get("odds") is None and db.get("odds_decimal") is not None:
            db["odds"] = db.get("odds_decimal")
        out.append(db)
    return out

def main():
    all_rows = []
    sports = [s.strip().upper() for s in os.getenv("PROP_HUNTER_SPORTS", "MLB,NBA,WNBA,NFL").split(",") if s.strip()]

    # Quellen-Kette pro Sport: jede in try, keine blockiert die andere.
    # Odds-Quellen (echte Quoten): Bovada, FanDuel, DraftKings
    # Linien-Quellen (unpriced pick’em lines for modelling): PrizePicks, Underdog, Sleeper
    skip_blocked = str(os.getenv("PH_SKIP_BLOCKED_FREE", "0")).lower() in {"1", "true", "yes", "on"}
    per_sport_sources = [] if skip_blocked else [
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
            db_rows = _snapshot_db_rows(uniq)
            # Keep writes small enough for Supabase Free and PostgREST schema cache.
            for i in range(0, len(db_rows), 200):
                upsert_rows("prop_hunter_prop_snapshots", db_rows[i:i + 200], "snapshot_id")
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
