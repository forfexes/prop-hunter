#!/usr/bin/env python3
"""PROP HUNTER — NCAA RESULTS (NCAAB + NCAAF)

Keyless ESPN public scoreboard/summary collector. It only inspects games tied to
pending college picks, writes player-level gamelogs, and uses the same normalized
columns as NBA/NFL so the generic settler/learning path works unchanged.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Set

from prop_hunter_shared_utils import (
    http_json, log, norm_name, safe_json_write, select_pick_rows, to_float,
    upsert_rows, warn
)

OUT = "prop_hunter_results_ncaa_raw.json"
SPORTS = {
    "NCAAB": ("basketball", "mens-college-basketball", "BASKETBALL"),
    "NCAAF": ("football", "college-football", "AMERICAN_FOOTBALL"),
}

def _pending(row: Dict[str, Any]) -> bool:
    return str(row.get("status") or row.get("result") or "pending").strip().lower() in {
        "", "pending", "open", "none", "null", "unsettled"
    }

def _league(row: Dict[str, Any]) -> str:
    s = str(row.get("league") or row.get("sport") or "").upper().replace("-", "").replace("_", "")
    if "NCAAB" in s or "COLLEGEBASKETBALL" in s:
        return "NCAAB"
    if "NCAAF" in s or "COLLEGEFOOTBALL" in s:
        return "NCAAF"
    return ""

def _date_only(value: Any):
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

def _pick_date(row: Dict[str, Any]):
    raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
    for value in (
        row.get("commence_time"), raw.get("commence_time"), row.get("game_date"),
        row.get("sent_date"), row.get("date"), row.get("created_at")
    ):
        d = _date_only(value)
        if d is not None:
            return d
    return datetime.now(timezone.utc).date()

def _pick_game_text(row: Dict[str, Any]) -> str:
    raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
    parts = [
        row.get("game"), row.get("team"), row.get("home_team"), row.get("away_team"),
        raw.get("game"), raw.get("home_team"), raw.get("away_team"),
    ]
    return " ".join(str(x or "") for x in parts).lower()

def pending_picks(league: str, limit: int = 5000) -> List[Dict[str, Any]]:
    out = []
    for row in select_pick_rows(limit=limit):
        if _pending(row) and _league(row) == league:
            name = str(row.get("player_name") or row.get("player") or row.get("selection") or "").strip()
            if name:
                out.append(dict(row, _wanted_player=name))
    return out

def _team_names(event: Dict[str, Any]) -> List[str]:
    names = []
    comp = (event.get("competitions") or [{}])[0]
    for c in comp.get("competitors") or []:
        t = c.get("team") or {}
        for key in ("displayName", "shortDisplayName", "name", "abbreviation"):
            if t.get(key):
                names.append(str(t[key]).lower())
    return names

def _event_matches_pick(event: Dict[str, Any], pick: Dict[str, Any]) -> bool:
    game = _pick_game_text(pick)
    if not game:
        return True
    names = _team_names(event)
    if not names:
        return True
    hits = 0
    for name in names:
        tokens = [t for t in re.split(r"[^a-z0-9]+", name) if len(t) >= 4]
        if name in game or any(t in game for t in tokens):
            hits += 1
    return hits >= 1

def scoreboard(league: str, yyyymmdd: str) -> List[Dict[str, Any]]:
    sport, slug, _ = SPORTS[league]
    url = f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{slug}/scoreboard"
    data = http_json(url, params={"dates": yyyymmdd, "limit": 200}, retries=1) or {}
    return [x for x in (data.get("events") or []) if isinstance(x, dict)]

def summary(league: str, event_id: str) -> Dict[str, Any]:
    sport, slug, _ = SPORTS[league]
    url = f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{slug}/summary"
    return http_json(url, params={"event": event_id}, retries=1) or {}

def _keys(block: Dict[str, Any]) -> List[str]:
    seq = block.get("keys") or block.get("labels") or []
    return [
        re.sub(r"[^a-z0-9]+", "_", str(x or "").strip().lower()).strip("_")
        for x in seq
    ]

def _num(value: Any) -> Optional[float]:
    if value in (None, "", "--"):
        return None
    s = str(value).strip()
    if re.fullmatch(r"\d+(?:\.\d+)?[-/]\d+(?:\.\d+)?", s):
        s = re.split(r"[-/]", s, 1)[0]
    return to_float(s)

def _event_date(payload: Dict[str, Any]) -> Optional[str]:
    header = payload.get("header") or {}
    comp = (header.get("competitions") or [{}])[0]
    value = comp.get("date") or header.get("date")
    return str(value)[:10] if value else None

def _season_for(league: str, game_date: Optional[str]) -> str:
    d = _date_only(game_date) or datetime.now(timezone.utc).date()
    if league == "NCAAB" and d.month <= 6:
        return str(d.year - 1)
    return str(d.year)

def _base_row(league: str, event_id: str, game_date: Optional[str], team: str, name: str) -> Dict[str, Any]:
    return {
        "sport": SPORTS[league][2],
        "league": league,
        "country": "USA",
        "season": _season_for(league, game_date),
        "source": "espn_summary",
        "source_game_id": str(event_id),
        "game_id": str(event_id),
        "game_date": game_date,
        "player_name": name,
        "normalized_name": norm_name(name),
        "team": team,
    }

def parse_ncaab_summary(payload: Dict[str, Any], wanted: Iterable[str] = ()) -> List[Dict[str, Any]]:
    wanted_n = {norm_name(x) for x in wanted if x}
    event_id = str((payload.get("header") or {}).get("id") or payload.get("id") or "")
    game_date = _event_date(payload)
    rows = []
    for team_block in ((payload.get("boxscore") or {}).get("players") or []):
        team_obj = team_block.get("team") or {}
        team = team_obj.get("displayName") or team_obj.get("abbreviation") or ""
        merged: Dict[str, Dict[str, Any]] = {}
        for block in team_block.get("statistics") or []:
            keys = _keys(block)
            for athlete in block.get("athletes") or []:
                info = athlete.get("athlete") or {}
                name = info.get("displayName") or info.get("shortName")
                if not name:
                    continue
                nn = norm_name(name)
                if wanted_n and nn not in wanted_n:
                    continue
                rec = merged.setdefault(nn, {"name": name, "stats": {}})
                stats = athlete.get("stats") or []
                for i, key in enumerate(keys):
                    if i < len(stats):
                        rec["stats"][key] = stats[i]
        for rec in merged.values():
            s = rec["stats"]
            def get(*names):
                for key in names:
                    if key in s and s.get(key) not in (None, ""):
                        return _num(s.get(key))
                return None
            pts = get("pts", "points")
            reb = get("reb", "rebounds")
            ast = get("ast", "assists")
            threes = get("3pt", "fg3", "3pm", "three_point_field_goals")
            row = _base_row("NCAAB", event_id, game_date, team, rec["name"])
            row.update({
                "minutes": get("min", "minutes"),
                "points": pts,
                "rebounds": reb,
                "assists": ast,
                "pra": (pts + reb + ast) if None not in (pts, reb, ast) else None,
                "ra": (reb + ast) if None not in (reb, ast) else None,
                "threes_made": threes,
                "steals": get("stl", "steals"),
                "blocks": get("blk", "blocks"),
                "turnovers": get("to", "tov", "turnovers"),
                "double_double": (sum(1 for v in (pts, reb, ast) if v is not None and v >= 10) >= 2)
                    if any(v is not None for v in (pts, reb, ast)) else None,
                "triple_double": (sum(1 for v in (pts, reb, ast) if v is not None and v >= 10) >= 3)
                    if any(v is not None for v in (pts, reb, ast)) else None,
                "raw": {"stats": s, "team": team_obj},
            })
            rows.append(row)
    return rows

def parse_ncaaf_summary(payload: Dict[str, Any], wanted: Iterable[str] = ()) -> List[Dict[str, Any]]:
    wanted_n = {norm_name(x) for x in wanted if x}
    event_id = str((payload.get("header") or {}).get("id") or payload.get("id") or "")
    game_date = _event_date(payload)
    rows = []
    for team_block in ((payload.get("boxscore") or {}).get("players") or []):
        team_obj = team_block.get("team") or {}
        team = team_obj.get("displayName") or team_obj.get("abbreviation") or ""
        merged: Dict[str, Dict[str, Any]] = {}
        for block in team_block.get("statistics") or []:
            category = str(block.get("name") or block.get("displayName") or "").lower()
            keys = _keys(block)
            for athlete in block.get("athletes") or []:
                info = athlete.get("athlete") or {}
                name = info.get("displayName") or info.get("shortName")
                if not name:
                    continue
                nn = norm_name(name)
                if wanted_n and nn not in wanted_n:
                    continue
                rec = merged.setdefault(nn, {"name": name, "cats": {}})
                vals = {}
                stats = athlete.get("stats") or []
                for i, key in enumerate(keys):
                    if i < len(stats):
                        vals[key] = stats[i]
                rec["cats"][category] = vals
        for rec in merged.values():
            row = _base_row("NCAAF", event_id, game_date, team, rec["name"])
            raw_cats = rec["cats"]
            for cat, s in raw_cats.items():
                def get(*names):
                    for key in names:
                        if key in s and s.get(key) not in (None, ""):
                            return _num(s.get(key))
                    return None
                if "pass" in cat:
                    row["passing_yards"] = get("yds", "yards")
                    row["passing_touchdowns"] = get("td", "tds")
                    row["interceptions"] = get("int", "interceptions")
                elif "rush" in cat:
                    row["rushing_attempts"] = get("car", "att", "attempts")
                    row["rushing_yards"] = get("yds", "yards")
                    row["rushing_touchdowns"] = get("td", "tds")
                elif "receiv" in cat:
                    row["receptions"] = get("rec", "receptions")
                    row["receiving_yards"] = get("yds", "yards")
                    row["receiving_touchdowns"] = get("td", "tds")
                    row["targets"] = get("tgts", "targets")
            rush_td = to_float(row.get("rushing_touchdowns"), 0.0) or 0.0
            rec_td = to_float(row.get("receiving_touchdowns"), 0.0) or 0.0
            total_td = rush_td + rec_td
            row.update({
                "touchdowns": total_td,
                "anytime_td": 1.0 if total_td >= 1 else 0.0,
                "two_plus_td": 1.0 if total_td >= 2 else 0.0,
                "three_plus_td": 1.0 if total_td >= 3 else 0.0,
                "raw": {"categories": raw_cats, "team": team_obj},
            })
            rows.append(row)
    return rows

def _resolve_events(league: str, picks: List[Dict[str, Any]]) -> Dict[str, Set[str]]:
    by_date: Dict[str, List[Dict[str, Any]]] = {}
    for p in picks:
        d = _pick_date(p)
        for dd in (d - timedelta(days=1), d, d + timedelta(days=1)):
            by_date.setdefault(dd.strftime("%Y%m%d"), []).append(p)

    resolved: Dict[str, Set[str]] = {}
    max_dates = max(1, int(os.getenv("PH_NCAA_RESULTS_MAX_DATES", "5")))
    max_events = max(1, int(os.getenv("PH_NCAA_RESULTS_MAX_EVENTS", "24")))
    seen_events = set()
    for ymd, date_picks in list(by_date.items())[:max_dates]:
        for event in scoreboard(league, ymd):
            eid = str(event.get("id") or "")
            if not eid or eid in seen_events:
                continue
            matches = [p for p in date_picks if _event_matches_pick(event, p)]
            if not matches:
                continue
            seen_events.add(eid)
            resolved[eid] = {str(p.get("_wanted_player") or "") for p in matches if p.get("_wanted_player")}
            if len(resolved) >= max_events:
                return resolved
    return resolved

def collect_league(league: str) -> List[Dict[str, Any]]:
    picks = pending_picks(league, limit=int(os.getenv("NCAA_PICK_SCAN_LIMIT", "5000")))
    if not picks:
        log(f"{league} results: no pending picks")
        return []
    event_players = _resolve_events(league, picks)
    parser = parse_ncaab_summary if league == "NCAAB" else parse_ncaaf_summary
    rows = []
    for event_id, players in event_players.items():
        try:
            payload = summary(league, event_id)
            rows.extend(parser(payload, players))
        except Exception as exc:
            warn(f"{league} summary failed event={event_id}: {exc}")
    log(f"{league} results: pending={len(picks)} events={len(event_players)} rows={len(rows)}")
    return rows

def main() -> None:
    leagues = [
        x.strip().upper() for x in os.getenv("PH_NCAA_RESULT_LEAGUES", "NCAAB,NCAAF").split(",")
        if x.strip().upper() in SPORTS
    ]
    rows: List[Dict[str, Any]] = []
    for league in leagues:
        rows.extend(collect_league(league))
    safe_json_write(OUT, rows)
    if rows:
        upsert_rows(
            "prop_hunter_player_gamelogs", rows,
            "sport,league,season,game_id,normalized_name"
        )
    log(f"NCAA results done: leagues={','.join(leagues)} rows={len(rows)}")

if __name__ == "__main__":
    main()
