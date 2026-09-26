#!/usr/bin/env python3
"""PROP HUNTER — NCAAB/NCAAF results and player gamelogs.

Uses ESPN public scoreboard/summary JSON only.  The collector is pending-pick driven:
it looks only at dates/players currently needed for settlement and never sweeps a
whole season.  Pure parser functions are kept separate so the daily hard-test can
exercise college settlement without network calls.
"""
from __future__ import annotations

import os
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Tuple

from prop_hunter_shared_utils import (
    http_json, log, norm_name, safe_json_write, select_pick_rows, to_float,
    upsert_rows, warn,
)

OUT = "prop_hunter_results_college_raw.json"
SPORTS = {
    "NCAAB": ("basketball", "mens-college-basketball"),
    "NCAAF": ("football", "college-football"),
}


def _date_only(value: Any) -> date | None:
    if not value:
        return None
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except Exception:
        try:
            return date.fromisoformat(text[:10])
        except Exception:
            return None


def _pending(row: Dict[str, Any]) -> bool:
    return str(row.get("status") or row.get("result") or "pending").lower().strip() in {"", "pending", "open", "none", "null"}


def _college_league(row: Dict[str, Any]) -> str | None:
    sport = str(row.get("sport") or "").upper()
    league = str(row.get("league") or "").upper()
    text = f"{sport} {league}"
    if "NCAAB" in text or "COLLEGE BASKET" in text:
        return "NCAAB"
    if "NCAAF" in text or "COLLEGE FOOT" in text:
        return "NCAAF"
    return None


def pending_targets(limit: int = 5000) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {"NCAAB": [], "NCAAF": []}
    for row in select_pick_rows(limit=limit):
        league = _college_league(row)
        if not league or not _pending(row):
            continue
        player = str(row.get("player_name") or row.get("player") or "").strip()
        if not player:
            continue
        raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
        d = None
        for v in (row.get("commence_time"), raw.get("commence_time"), row.get("game_date"), row.get("date"), row.get("sent_date"), row.get("created_at")):
            d = _date_only(v)
            if d:
                break
        if not d:
            continue
        out[league].append({
            "player": player,
            "name_key": norm_name(player),
            "date": d,
            "game": str(row.get("game") or raw.get("game") or ""),
            "home": str(row.get("home") or raw.get("home_team") or ""),
            "away": str(row.get("away") or raw.get("away_team") or ""),
        })
    return out


def _num(v: Any) -> float | None:
    if v in (None, "", "--"):
        return None
    text = str(v).strip()
    if "-" in text and re.fullmatch(r"\d+\s*-\s*\d+", text):
        text = text.split("-", 1)[0]
    return to_float(text)


def _stat_map(block: Dict[str, Any], athlete_row: Dict[str, Any]) -> Dict[str, Any]:
    values = list(athlete_row.get("stats") or [])
    keys = list(block.get("keys") or [])
    labels = list(block.get("labels") or [])
    names = keys if len(keys) == len(values) else labels if len(labels) == len(values) else [str(i) for i in range(len(values))]
    out = {}
    for k, v in zip(names, values):
        nk = re.sub(r"[^a-z0-9]+", "", str(k).lower())
        out[nk] = v
    return out


def _pick_stat(stats: Dict[str, Any], *aliases: str) -> float | None:
    for alias in aliases:
        key = re.sub(r"[^a-z0-9]+", "", alias.lower())
        if key in stats:
            return _num(stats.get(key))
    return None


def _game_meta(summary: Dict[str, Any], league: str, event_id: str = "") -> Tuple[str, str | None, Dict[str, str]]:
    header = summary.get("header") or {}
    comps = header.get("competitions") or []
    comp = comps[0] if comps else {}
    game_id = str(comp.get("id") or header.get("id") or event_id)
    game_date = str(comp.get("date") or header.get("date") or "")[:10] or None
    teams = {}
    for c in comp.get("competitors") or []:
        team = c.get("team") or {}
        name = str(team.get("displayName") or team.get("shortDisplayName") or team.get("name") or "")
        if name:
            teams[str(team.get("id") or name)] = name
    return game_id, game_date, teams


def parse_ncaab_summary(summary: Dict[str, Any], event_id: str = "") -> List[Dict[str, Any]]:
    if not isinstance(summary, dict):
        return []
    game_id, game_date, teams = _game_meta(summary, "NCAAB", event_id)
    rows = []
    for team_block in ((summary.get("boxscore") or {}).get("players") or []):
        team = team_block.get("team") or {}
        team_name = str(team.get("displayName") or team.get("shortDisplayName") or team.get("name") or "")
        for block in team_block.get("statistics") or []:
            for a in block.get("athletes") or []:
                athlete = a.get("athlete") or {}
                name = str(athlete.get("displayName") or athlete.get("fullName") or "").strip()
                if not name:
                    continue
                sm = _stat_map(block, a)
                pts = _pick_stat(sm, "points", "pts")
                reb = _pick_stat(sm, "rebounds", "reb")
                ast = _pick_stat(sm, "assists", "ast")
                threes = _pick_stat(sm, "threePointFieldGoalsMade-threePointFieldGoalsAttempted", "3pt", "3pm", "threePointFieldGoalsMade")
                stl = _pick_stat(sm, "steals", "stl")
                blk = _pick_stat(sm, "blocks", "blk")
                tov = _pick_stat(sm, "turnovers", "to")
                # Ignore roster/stat sections that do not contain actual boxscore stats.
                if all(v is None for v in (pts, reb, ast, threes, stl, blk, tov)):
                    continue
                rows.append({
                    "sport": "BASKETBALL", "league": "NCAAB", "season": str(datetime.now(timezone.utc).year),
                    "source": "espn_summary", "source_game_id": game_id, "game_id": game_id,
                    "game_date": game_date, "player_name": name, "normalized_name": norm_name(name),
                    "team": team.get("abbreviation") or team_name,
                    "points": pts, "rebounds": reb, "assists": ast, "threes_made": threes,
                    "steals": stl, "blocks": blk, "turnovers": tov,
                    "pra": (pts + reb + ast) if all(v is not None for v in (pts, reb, ast)) else None,
                    "ra": (reb + ast) if reb is not None and ast is not None else None,
                    "double_double": (sum(1 for v in (pts, reb, ast, stl, blk) if v is not None and v >= 10) >= 2),
                    "triple_double": (sum(1 for v in (pts, reb, ast, stl, blk) if v is not None and v >= 10) >= 3),
                    "raw": {"block": block.get("name"), "stats": sm, "athlete": a},
                })
    return _dedupe_player_game(rows)


def parse_ncaaf_summary(summary: Dict[str, Any], event_id: str = "") -> List[Dict[str, Any]]:
    if not isinstance(summary, dict):
        return []
    game_id, game_date, teams = _game_meta(summary, "NCAAF", event_id)
    merged: Dict[str, Dict[str, Any]] = {}
    for team_block in ((summary.get("boxscore") or {}).get("players") or []):
        team = team_block.get("team") or {}
        team_name = str(team.get("displayName") or team.get("shortDisplayName") or team.get("name") or "")
        for block in team_block.get("statistics") or []:
            section = str(block.get("name") or "").lower()
            for a in block.get("athletes") or []:
                athlete = a.get("athlete") or {}
                name = str(athlete.get("displayName") or athlete.get("fullName") or "").strip()
                if not name:
                    continue
                key = norm_name(name)
                row = merged.setdefault(key, {
                    "sport": "AMERICAN_FOOTBALL", "league": "NCAAF", "season": str(datetime.now(timezone.utc).year),
                    "source": "espn_summary", "source_game_id": game_id, "game_id": game_id,
                    "game_date": game_date, "player_name": name, "normalized_name": key,
                    "team": team.get("abbreviation") or team_name, "raw": {},
                })
                sm = _stat_map(block, a)
                row["raw"][section or "stats"] = sm
                if "pass" in section:
                    row["passing_yards"] = _pick_stat(sm, "passingYards", "yds", "yards")
                    row["passing_touchdowns"] = _pick_stat(sm, "passingTouchdowns", "td")
                    row["interceptions"] = _pick_stat(sm, "interceptions", "int")
                elif "rush" in section:
                    row["rushing_attempts"] = _pick_stat(sm, "rushingAttempts", "car", "carries")
                    row["rushing_yards"] = _pick_stat(sm, "rushingYards", "yds", "yards")
                    row["rushing_touchdowns"] = _pick_stat(sm, "rushingTouchdowns", "td")
                elif "receiv" in section:
                    row["receptions"] = _pick_stat(sm, "receptions", "rec")
                    row["receiving_yards"] = _pick_stat(sm, "receivingYards", "yds", "yards")
                    row["receiving_touchdowns"] = _pick_stat(sm, "receivingTouchdowns", "td")
                    row["targets"] = _pick_stat(sm, "receivingTargets", "targets", "tgts")
    out = []
    for row in merged.values():
        rec = to_float(row.get("receiving_touchdowns"), 0.0) or 0.0
        rush = to_float(row.get("rushing_touchdowns"), 0.0) or 0.0
        total = rec + rush
        row["touchdowns"] = total
        row["anytime_td"] = 1.0 if total >= 1 else 0.0
        row["two_plus_td"] = 1.0 if total >= 2 else 0.0
        row["three_plus_td"] = 1.0 if total >= 3 else 0.0
        if any(row.get(k) is not None for k in ("passing_yards", "passing_touchdowns", "rushing_yards", "receiving_yards", "receptions", "touchdowns")):
            out.append(row)
    return out


def _dedupe_player_game(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in rows:
        key = (str(row.get("game_id") or ""), str(row.get("normalized_name") or ""))
        if key not in merged:
            merged[key] = dict(row)
        else:
            cur = merged[key]
            for k, v in row.items():
                if v is not None and k != "raw":
                    cur[k] = v
                elif k == "raw":
                    cur.setdefault("raw", {}).update(v if isinstance(v, dict) else {})
    return list(merged.values())


def _scoreboard(league: str, d: date) -> List[Dict[str, Any]]:
    sport, slug = SPORTS[league]
    url = f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{slug}/scoreboard"
    data = http_json(url, params={"dates": d.strftime("%Y%m%d"), "limit": 300}, retries=1) or {}
    return list(data.get("events") or [])


def _summary(league: str, event_id: str) -> Dict[str, Any]:
    sport, slug = SPORTS[league]
    url = f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{slug}/summary"
    return http_json(url, params={"event": event_id}, retries=1) or {}


def _event_text(ev: Dict[str, Any]) -> str:
    parts = [str(ev.get("name") or ev.get("shortName") or "")]
    for comp in ev.get("competitions") or []:
        for c in comp.get("competitors") or []:
            t = c.get("team") or {}
            parts.extend([str(t.get("displayName") or ""), str(t.get("shortDisplayName") or ""), str(t.get("abbreviation") or "")])
    return norm_name(" ".join(parts))


def _event_matches_targets(ev: Dict[str, Any], targets: List[Dict[str, Any]]) -> bool:
    text = _event_text(ev)
    for t in targets:
        hints = [t.get("game"), t.get("home"), t.get("away")]
        for hint in hints:
            h = norm_name(hint)
            if h and (h in text or any(tok and tok in text for tok in h.split() if len(tok) >= 4)):
                return True
    return False


def _filter_players(rows: List[Dict[str, Any]], targets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    wanted = {t["name_key"] for t in targets}
    if not wanted:
        return []
    out = []
    for row in rows:
        key = norm_name(row.get("player_name"))
        if key in wanted or any(key and (key in w or w in key) for w in wanted):
            out.append(row)
    return out


def main() -> None:
    targets_by_league = pending_targets(limit=int(os.getenv("COLLEGE_PICK_SCAN_LIMIT", "5000")))
    event_cap = max(1, int(os.getenv("PH_COLLEGE_RESULTS_EVENT_CAP", "30")))
    all_rows: List[Dict[str, Any]] = []
    for league, targets in targets_by_league.items():
        if not targets:
            continue
        dates = sorted({t["date"] for t in targets})[-4:]
        fetch_dates = sorted({d + timedelta(days=off) for d in dates for off in (-1, 0, 1)})
        seen_events = set()
        fetched = 0
        for d in fetch_dates:
            if fetched >= event_cap:
                break
            try:
                events = _scoreboard(league, d)
            except Exception as exc:
                warn(f"{league} scoreboard failed {d}: {exc}")
                continue
            for ev in events:
                eid = str(ev.get("id") or "")
                if not eid or eid in seen_events or fetched >= event_cap:
                    continue
                if not _event_matches_targets(ev, targets):
                    continue
                seen_events.add(eid); fetched += 1
                try:
                    data = _summary(league, eid)
                    parsed = parse_ncaab_summary(data, eid) if league == "NCAAB" else parse_ncaaf_summary(data, eid)
                    all_rows.extend(_filter_players(parsed, targets))
                except Exception as exc:
                    warn(f"{league} summary failed event={eid}: {exc}")
        log(f"{league} results: pending_players={len({t['name_key'] for t in targets})} events={fetched}")

    all_rows = _dedupe_player_game(all_rows)
    safe_json_write(OUT, all_rows)
    if all_rows:
        upsert_rows("prop_hunter_player_gamelogs", all_rows, "sport,league,season,game_id,normalized_name")
    log(f"college results done: rows={len(all_rows)}")


if __name__ == "__main__":
    main()
