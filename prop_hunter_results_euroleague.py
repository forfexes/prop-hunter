#!/usr/bin/env python3
"""PROP HUNTER — EUROLEAGUE RESULTS

Keyless ESPN public scoreboard/summary collector. It only inspects games tied to
pending EuroLeague picks and writes normalized player-level gamelogs so the
existing basketball settler and learning pipeline can grade them unchanged.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Set

from prop_hunter_shared_utils import (
    http_json, log, norm_name, safe_json_write, select_pick_rows, to_float,
    upsert_rows, warn,
)

OUT = "prop_hunter_results_euroleague_raw.json"
SPORT = "BASKETBALL"
LEAGUE = "EUROLEAGUE"
ESPN_SPORT = "basketball"
ESPN_LEAGUE = "euroleague"


def _pending(row: Dict[str, Any]) -> bool:
    return str(row.get("status") or row.get("result") or "pending").strip().lower() in {
        "", "pending", "open", "none", "null", "unsettled"
    }


def _is_euroleague(row: Dict[str, Any]) -> bool:
    text = " ".join(str(row.get(k) or "") for k in ("league", "sport", "source_sport")).upper()
    text = text.replace("-", "").replace("_", "").replace(" ", "")
    return "EUROLEAGUE" in text or "BASKETBALLEUROLEAGUE" in text


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
        row.get("sent_date"), row.get("date"), row.get("created_at"),
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


def pending_picks(limit: int = 5000) -> List[Dict[str, Any]]:
    out = []
    for row in select_pick_rows(limit=limit):
        if not _pending(row) or not _is_euroleague(row):
            continue
        name = str(row.get("player_name") or row.get("player") or row.get("selection") or "").strip()
        if name:
            out.append(dict(row, _wanted_player=name))
    return out


def scoreboard(yyyymmdd: str) -> List[Dict[str, Any]]:
    url = f"https://site.api.espn.com/apis/site/v2/sports/{ESPN_SPORT}/{ESPN_LEAGUE}/scoreboard"
    data = http_json(url, params={"dates": yyyymmdd, "limit": 100}, retries=1) or {}
    return [x for x in (data.get("events") or []) if isinstance(x, dict)]


def summary(event_id: str) -> Dict[str, Any]:
    url = f"https://site.api.espn.com/apis/site/v2/sports/{ESPN_SPORT}/{ESPN_LEAGUE}/summary"
    return http_json(url, params={"event": event_id}, retries=1) or {}


def _team_names(event: Dict[str, Any]) -> List[str]:
    names: List[str] = []
    comp = (event.get("competitions") or [{}])[0]
    for competitor in comp.get("competitors") or []:
        team = competitor.get("team") or {}
        for key in ("displayName", "shortDisplayName", "name", "abbreviation"):
            if team.get(key):
                names.append(str(team[key]).lower())
    return names


def _event_matches_pick(event: Dict[str, Any], pick: Dict[str, Any]) -> bool:
    game = _pick_game_text(pick)
    if not game:
        return True
    names = _team_names(event)
    if not names:
        return True
    for name in names:
        tokens = [t for t in re.split(r"[^a-z0-9]+", name) if len(t) >= 4]
        if name in game or any(t in game for t in tokens):
            return True
    return False


def _keys(block: Dict[str, Any]) -> List[str]:
    seq = block.get("keys") or block.get("labels") or []
    return [re.sub(r"[^a-z0-9]+", "_", str(x or "").strip().lower()).strip("_") for x in seq]


def _num(value: Any) -> Optional[float]:
    if value in (None, "", "--"):
        return None
    s = str(value).strip()
    if re.fullmatch(r"\d+(?:\.\d+)?\s*[-/]\s*\d+(?:\.\d+)?", s):
        s = re.split(r"[-/]", s, 1)[0].strip()
    return to_float(s)


def _event_date(payload: Dict[str, Any]) -> Optional[str]:
    header = payload.get("header") or {}
    comp = (header.get("competitions") or [{}])[0]
    value = comp.get("date") or header.get("date")
    return str(value)[:10] if value else None


def _season_for(game_date: Optional[str]) -> str:
    d = _date_only(game_date) or datetime.now(timezone.utc).date()
    return str(d.year - 1 if d.month <= 7 else d.year)


def _get_stat(stats: Dict[str, Any], *names: str) -> Optional[float]:
    for key in names:
        if key in stats and stats.get(key) not in (None, ""):
            return _num(stats.get(key))
    return None


def parse_summary(payload: Dict[str, Any], wanted: Iterable[str] = ()) -> List[Dict[str, Any]]:
    wanted_n = {norm_name(x) for x in wanted if x}
    header = payload.get("header") or {}
    event_id = str(header.get("id") or payload.get("id") or "")
    game_date = _event_date(payload)
    rows: List[Dict[str, Any]] = []
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
                values = athlete.get("stats") or []
                for i, key in enumerate(keys):
                    if i < len(values):
                        rec["stats"][key] = values[i]
        for rec in merged.values():
            s = rec["stats"]
            pts = _get_stat(s, "pts", "points")
            reb = _get_stat(s, "reb", "rebounds", "totreb", "total_rebounds")
            ast = _get_stat(s, "ast", "assists")
            threes = _get_stat(s, "3pt", "fg3", "3pm", "three_point_field_goals", "three_point_field_goals_made")
            stl = _get_stat(s, "stl", "steals")
            blk = _get_stat(s, "blk", "blocks")
            vals_for_double = [v for v in (pts, reb, ast, stl, blk) if v is not None]
            rows.append({
                "sport": SPORT, "league": LEAGUE, "country": "EU", "season": _season_for(game_date),
                "source": "espn_summary", "source_game_id": event_id, "game_id": event_id, "game_date": game_date,
                "player_name": rec["name"], "normalized_name": norm_name(rec["name"]), "team": team,
                "minutes": _get_stat(s, "min", "minutes"), "points": pts, "rebounds": reb, "assists": ast,
                "pra": (pts + reb + ast) if None not in (pts, reb, ast) else None,
                "pr": (pts + reb) if None not in (pts, reb) else None,
                "pa": (pts + ast) if None not in (pts, ast) else None,
                "ra": (reb + ast) if None not in (reb, ast) else None,
                "threes_made": threes, "steals": stl, "blocks": blk,
                "turnovers": _get_stat(s, "to", "tov", "turnovers"),
                "double_double": (sum(1 for v in vals_for_double if v >= 10) >= 2) if vals_for_double else None,
                "triple_double": (sum(1 for v in vals_for_double if v >= 10) >= 3) if vals_for_double else None,
                "raw": {"stats": s, "team": team_obj},
            })
    return rows


def _resolve_events(picks: List[Dict[str, Any]]) -> Dict[str, Set[str]]:
    by_date: Dict[str, List[Dict[str, Any]]] = {}
    for pick in picks:
        d = _pick_date(pick)
        for dd in (d - timedelta(days=1), d, d + timedelta(days=1)):
            by_date.setdefault(dd.strftime("%Y%m%d"), []).append(pick)
    resolved: Dict[str, Set[str]] = {}
    max_dates = max(1, int(os.getenv("PH_EUROLEAGUE_RESULTS_MAX_DATES", "5")))
    max_events = max(1, int(os.getenv("PH_EUROLEAGUE_RESULTS_MAX_EVENTS", "20")))
    seen_events: Set[str] = set()
    for ymd, date_picks in list(by_date.items())[:max_dates]:
        for event in scoreboard(ymd):
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


def main() -> None:
    picks = pending_picks(limit=int(os.getenv("EUROLEAGUE_PICK_SCAN_LIMIT", "5000")))
    if not picks:
        safe_json_write(OUT, [])
        log("EUROLEAGUE results: no pending picks")
        return
    event_players = _resolve_events(picks)
    rows: List[Dict[str, Any]] = []
    for event_id, players in event_players.items():
        try:
            rows.extend(parse_summary(summary(event_id), players))
        except Exception as exc:
            warn(f"EUROLEAGUE summary failed event={event_id}: {exc}")
    safe_json_write(OUT, rows)
    if rows:
        upsert_rows("prop_hunter_player_gamelogs", rows, "sport,league,season,game_id,normalized_name")
    log(f"EUROLEAGUE results done: pending={len(picks)} events={len(event_players)} rows={len(rows)}")


if __name__ == "__main__":
    main()
