#!/usr/bin/env python3
"""PROP HUNTER — NBA RESULTS

Pending-pick-driven NBA gamelogs. Primary: nba_api for explicitly selected
players. Fallback: public ESPN scoreboard + summary for the exact pending games.
Never sweeps the complete NBA player list.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from prop_hunter_shared_utils import (
    http_json, log, norm_name, safe_json_write, select_pick_rows, to_float,
    upsert_rows, warn
)

OUT = "prop_hunter_results_nba_raw.json"

def current_nba_season(now=None):
    now = now or datetime.now(timezone.utc)
    # Treat September as the upcoming season so preseason picks in late September
    # are not queried against the previous year's player logs.
    start = now.year if now.month >= 9 else now.year - 1
    return f"{start}-{(start+1)%100:02d}"

def _pending(row):
    return str(row.get("status") or row.get("result") or "pending").strip().lower() in {
        "", "pending", "open", "none", "null", "unsettled"
    }

def _is_nba(row):
    return str(row.get("league") or row.get("sport") or "").upper() == "NBA"

def _date_only(value):
    if not value:
        return None
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except Exception:
        try:
            return datetime.fromisoformat(text[:10]).date()
        except Exception:
            return None

def _pick_date(row):
    raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
    for v in (
        row.get("commence_time"), raw.get("commence_time"), row.get("game_date"),
        row.get("sent_date"), row.get("date"), row.get("created_at")
    ):
        d = _date_only(v)
        if d:
            return d
    return datetime.now(timezone.utc).date()

def _game_text(row):
    raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
    return " ".join(str(x or "") for x in (
        row.get("game"), row.get("team"), row.get("home_team"), row.get("away_team"),
        raw.get("game"), raw.get("home_team"), raw.get("away_team")
    )).lower()

def pending_picks(limit=5000):
    return [r for r in select_pick_rows(limit=limit) if _pending(r) and _is_nba(r)]

def pending_players(picks):
    seen = {}
    for r in picks:
        n = str(r.get("player_name") or r.get("player") or "").strip()
        if n:
            seen.setdefault(norm_name(n), n)
    return list(seen.values())[:max(1, int(os.getenv("NBA_RESULTS_PLAYER_CAP", "40")))]

def nba_api_player_logs(players=None, season=None, last_n=20):
    try:
        from nba_api.stats.static import players as nba_players
        from nba_api.stats.endpoints import playergamelog
    except Exception as e:
        warn(f"nba_api unavailable: {e}")
        return []
    season = season or os.getenv("NBA_SEASON") or current_nba_season()
    wanted = {norm_name(x) for x in (players or []) if x}
    if not wanted:
        log("NBA results: no pending players -> skip nba_api")
        return []
    all_players = nba_players.get_players()
    selected = [p for p in all_players if norm_name(p.get("full_name")) in wanted]
    if not selected:
        for p in all_players:
            pn = norm_name(p.get("full_name"))
            if any(w in pn or pn in w for w in wanted):
                selected.append(p)
    rows = []
    api_timeout = int(os.getenv("NBA_RESULTS_TIMEOUT", "8"))
    for p in selected[:int(os.getenv("NBA_RESULTS_PLAYER_CAP", "40"))]:
        full = p.get("full_name")
        try:
            gl = playergamelog.PlayerGameLog(
                player_id=p.get("id"), season=season,
                season_type_all_star=os.getenv("NBA_SEASON_TYPE", "Regular Season"),
                timeout=api_timeout,
            )
            df = gl.get_data_frames()[0]
        except Exception as e:
            warn(f"NBA gamelog failed {full}: {e}")
            continue
        for _, r in df.head(last_n).iterrows():
            pts = to_float(r.get("PTS"), 0) or 0
            reb = to_float(r.get("REB"), 0) or 0
            ast = to_float(r.get("AST"), 0) or 0
            gid = str(r.get("Game_ID") or r.get("GAME_ID") or "")
            rows.append({
                "sport": "BASKETBALL", "league": "NBA", "season": season, "source": "nba_api",
                "source_game_id": gid, "game_id": gid,
                "game_date": str(r.get("GAME_DATE"))[:10] if r.get("GAME_DATE") is not None else None,
                "player_name": full, "normalized_name": norm_name(full), "opponent": str(r.get("MATCHUP") or ""),
                "minutes": to_float(r.get("MIN")), "points": pts, "rebounds": reb, "assists": ast,
                "pra": pts + reb + ast, "ra": reb + ast, "threes_made": to_float(r.get("FG3M")),
                "steals": to_float(r.get("STL")), "blocks": to_float(r.get("BLK")), "turnovers": to_float(r.get("TOV")),
                "double_double": sum(1 for v in (pts, reb, ast) if v >= 10) >= 2,
                "triple_double": sum(1 for v in (pts, reb, ast) if v >= 10) >= 3,
                "raw": dict(r),
            })
    return rows

def _made(v):
    if v in (None, "", "--"):
        return None
    s = str(v).strip()
    if re.fullmatch(r"\d+(?:\.\d+)?[-/]\d+(?:\.\d+)?", s):
        s = re.split(r"[-/]", s, 1)[0]
    return to_float(s)

def espn_scoreboard(ymd):
    url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
    return (http_json(url, params={"dates": ymd}, retries=1) or {}).get("events", []) or []

def _event_team_names(ev):
    comp = (ev.get("competitions") or [{}])[0]
    out = []
    for c in comp.get("competitors") or []:
        t = c.get("team") or {}
        for k in ("displayName", "shortDisplayName", "name", "abbreviation"):
            if t.get(k):
                out.append(str(t[k]).lower())
    return out

def _event_matches(ev, pick):
    game = _game_text(pick)
    if not game:
        return False
    # Require BOTH teams from the ESPN event to be represented in the quoted
    # sportsbook matchup. One shared city/nickname is not enough and previously
    # allowed players to be attached to the wrong NBA event.
    comp = (ev.get("competitions") or [{}])[0]
    matched_teams = 0
    for c in comp.get("competitors") or []:
        t = c.get("team") or {}
        variants = [str(t.get(k) or "").lower() for k in ("displayName","shortDisplayName","name","abbreviation")]
        variants = [v for v in variants if v]
        ok = any(v in game for v in variants)
        if not ok:
            tokens = {tok for v in variants for tok in re.split(r"[^a-z0-9]+", v) if len(tok) >= 4}
            ok = any(tok in game for tok in tokens)
        if ok:
            matched_teams += 1
    return matched_teams >= 2

def _espn_game_payload(game_id):
    url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary"
    data = http_json(url, params={"event": game_id}, retries=1) or {}
    if ((data.get("boxscore") or {}).get("players") or []):
        return data, "espn_summary"
    # Independent keyless ESPN CDN fallback. The payload mirrors the site
    # summary under gamepackageJSON and often survives site-summary gaps.
    cdn = http_json("https://cdn.espn.com/core/nba/boxscore",
                    params={"xhr": 1, "gameId": game_id}, retries=1) or {}
    package = cdn.get("gamepackageJSON") if isinstance(cdn, dict) else {}
    if isinstance(package, dict) and ((package.get("boxscore") or {}).get("players") or []):
        return package, "espn_cdn_boxscore"
    return data, "espn_summary"

def espn_summary_players(game_id, wanted):
    data, result_source = _espn_game_payload(game_id)
    wanted_n = {norm_name(x) for x in wanted if x}
    rows = []
    game_date = str(((data.get("header") or {}).get("competitions") or [{}])[0].get("date") or "")[:10]
    for tb in ((data.get("boxscore") or {}).get("players") or []):
        team = ((tb.get("team") or {}).get("displayName") or (tb.get("team") or {}).get("abbreviation"))
        for group in tb.get("statistics") or []:
            labels = group.get("labels") or group.get("keys") or []
            for ath in group.get("athletes") or []:
                info = ath.get("athlete") or {}
                name = info.get("displayName") or info.get("shortName")
                if not name or (wanted_n and norm_name(name) not in wanted_n):
                    continue
                vals = ath.get("stats") or []
                sm = {str(labels[i]).upper(): vals[i] for i in range(min(len(labels), len(vals)))}
                pts = to_float(sm.get("PTS"), 0) or 0
                reb = to_float(sm.get("REB"), 0) or 0
                ast = to_float(sm.get("AST"), 0) or 0
                rows.append({
                    "sport": "BASKETBALL", "league": "NBA", "season": current_nba_season(), "source": result_source,
                    "source_game_id": str(game_id), "game_id": str(game_id), "game_date": game_date,
                    "player_name": name, "normalized_name": norm_name(name), "team": team,
                    "minutes": to_float(sm.get("MIN")), "points": pts, "rebounds": reb, "assists": ast,
                    "pra": pts + reb + ast, "ra": reb + ast, "threes_made": _made(sm.get("3PM") or sm.get("3PT")),
                    "steals": to_float(sm.get("STL")), "blocks": to_float(sm.get("BLK")),
                    "turnovers": to_float(sm.get("TO") or sm.get("TOV")),
                    "double_double": sum(1 for v in (pts, reb, ast) if v >= 10) >= 2,
                    "triple_double": sum(1 for v in (pts, reb, ast) if v >= 10) >= 3,
                    "raw": {"stat_map": sm, "athlete": info},
                })
    return rows

def espn_pending_logs(picks):
    by_date = {}
    for p in picks:
        d = _pick_date(p)
        for dd in (d - timedelta(days=1), d, d + timedelta(days=1)):
            by_date.setdefault(dd.strftime("%Y%m%d"), []).append(p)
    max_dates = max(1, int(os.getenv("NBA_ESPN_MAX_DATES", "5")))
    max_events = max(1, int(os.getenv("NBA_ESPN_MAX_EVENTS", "16")))
    event_players = {}
    for ymd, ps in list(by_date.items())[:max_dates]:
        for ev in espn_scoreboard(ymd):
            eid = str(ev.get("id") or "")
            if not eid:
                continue
            matched = [p for p in ps if _event_matches(ev, p)]
            if not matched:
                continue
            event_players.setdefault(eid, set()).update(
                str(p.get("player_name") or p.get("player") or "").strip() for p in matched
            )
            if len(event_players) >= max_events:
                break
        if len(event_players) >= max_events:
            break
    rows = []
    for eid, names in event_players.items():
        rows.extend(espn_summary_players(eid, names))
    return rows

def dedupe_player_date(rows):
    priority = {"nba_api": 3, "espn_summary": 2, "espn_cdn_boxscore": 1}
    best = {}
    for r in rows:
        if not r.get("normalized_name") or not r.get("game_date"):
            continue
        k = (r.get("normalized_name"), r.get("game_date"))
        cur = best.get(k)
        if cur is None or priority.get(r.get("source"), 0) > priority.get(cur.get("source"), 0):
            best[k] = r
    return list(best.values())

def main():
    picks = pending_picks(limit=int(os.getenv("NBA_PICK_SCAN_LIMIT", "5000")))
    names = pending_players(picks)
    # ESPN event summaries are faster and event-scoped. stats.nba.com is kept as
    # an opt-in fallback because repeated PlayerGameLog calls routinely time out
    # on GitHub runners and can waste a full minute without adding a single row.
    rows = espn_pending_logs(picks)
    if str(os.getenv("PH_NBA_API_RESULTS_ENABLED", "0")).lower() in {"1","true","yes","on"}:
        rows.extend(nba_api_player_logs(names, last_n=int(os.getenv("LAST_N_GAMES", "20"))))
    else:
        log("NBA results: nba_api disabled; using event-scoped ESPN summaries")
    rows = dedupe_player_date(rows)
    safe_json_write(OUT, rows)
    if rows:
        upsert_rows("prop_hunter_player_gamelogs", rows, "sport,league,season,game_id,normalized_name")
    log(f"NBA results done: pending={len(picks)} players={len(names)} rows={len(rows)}")

if __name__ == "__main__":
    main()
