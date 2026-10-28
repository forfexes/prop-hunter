#!/usr/bin/env python3
"""PROP HUNTER — WNBA RESULTS

Pending-pick-driven ESPN scoreboard/summary collector. It fetches only games
linked to unresolved WNBA picks and writes player-level gamelogs.
"""
from __future__ import annotations

import os
from prop_hunter_basketball_boxscore import official_gameday, observed_stats
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from prop_hunter_shared_utils import (
    http_json, log, norm_name, safe_json_write, select_settlement_picks as select_pick_rows, to_float,
    upsert_rows, warn
)

OUT = "prop_hunter_results_wnba_raw.json"

def _wnba_season(date_value: str | None = None) -> str:
    env = str(os.getenv("WNBA_SEASON") or "").strip()
    if env:
        return env
    raw = str(date_value or "")
    m = re.search(r"(20\d{2})", raw)
    if m:
        return m.group(1)
    return str(datetime.now(timezone.utc).year)

def _pending(row):
    return str(row.get("status") or row.get("result") or "pending").strip().lower() in {
        "", "pending", "open", "none", "null", "unsettled"
    }

def _is_wnba(row):
    return str(row.get("league") or row.get("sport") or "").upper() == "WNBA"

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
    return [r for r in select_pick_rows(limit=limit) if _pending(r) and _is_wnba(r)]

def espn_scoreboard(ymd):
    url = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard"
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

def _event_final(ev):
    status = ev.get("status") or {}
    typ = status.get("type") or {}
    if typ.get("completed") is True:
        return True
    state = str(typ.get("state") or typ.get("name") or "").lower()
    return state in {"post", "final", "completed"}


def _event_matches(ev, pick):
    game = _game_text(pick)
    # Legacy PROP HUNTER rows often contain only player + pick date and no
    # matchup/team metadata.  In that case event matching is resolved safely
    # later by player presence in the final boxscore instead of rejecting every
    # event up front.
    if not game or game.strip() in {"wnba"}:
        return True
    matched = 0
    comp = (ev.get("competitions") or [{}])[0]
    for competitor in comp.get("competitors") or []:
        team = competitor.get("team") or {}
        variants = [str(team.get(k) or "").lower() for k in ("displayName","shortDisplayName","name","abbreviation")]
        variants = [v for v in variants if v]
        ok = any(v in game for v in variants)
        if not ok:
            toks = {t for v in variants for t in re.split(r"[^a-z0-9]+", v) if len(t) >= 4}
            ok = any(t in game for t in toks)
        if ok:
            matched += 1
    return matched >= 2

def _made(v):
    if v in (None, "", "--"):
        return None
    s = str(v).strip()
    if re.fullmatch(r"\d+(?:\.\d+)?[-/]\d+(?:\.\d+)?", s):
        s = re.split(r"[-/]", s, 1)[0]
    return to_float(s)

def espn_summary_players(game_id, wanted):
    url = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/summary"
    data = http_json(url, params={"event": game_id}, retries=1) or {}
    wanted_n = {norm_name(x) for x in wanted if x}
    rows = []
    start_time = ((data.get("header") or {}).get("competitions") or [{}])[0].get("date")
    game_date = official_gameday(start_time)
    for tb in ((data.get("boxscore") or {}).get("players") or []):
        team = ((tb.get("team") or {}).get("displayName") or (tb.get("team") or {}).get("abbreviation"))
        for group in tb.get("statistics") or []:
            labels = group.get("labels") or group.get("keys") or []
            for ath in group.get("athletes") or []:
                info = ath.get("athlete") or {}
                name = info.get("displayName") or info.get("shortName")
                if not name or (wanted_n and norm_name(name) not in wanted_n):
                    continue
                observed = observed_stats(group, ath)
                if not observed or not game_date:
                    continue
                sm = observed["stat_map"]
                pts, reb, ast = (observed[k] for k in ("points", "rebounds", "assists"))
                rows.append({
                    "sport": "BASKETBALL", "league": "WNBA", "season": _wnba_season(game_date), "source": "espn_summary",
                    "source_game_id": str(game_id), "game_id": str(game_id), "game_date": game_date,
                    "player_name": name, "normalized_name": norm_name(name), "team": team,
                    "minutes": to_float(sm.get("MIN")), "points": pts, "rebounds": reb, "assists": ast,
                    "pra": observed["pra"], "ra": observed["ra"], "threes_made": _made(sm.get("3PM") or sm.get("3PT")),
                    "steals": to_float(sm.get("STL")), "blocks": to_float(sm.get("BLK")),
                    "turnovers": to_float(sm.get("TO") or sm.get("TOV")),
                    "double_double": observed["double_double"],
                    "triple_double": observed["triple_double"],
                    "raw": {"stat_map": sm, "athlete": info, "start_time_utc": start_time},
                })
    return rows

def main():
    picks = pending_picks(limit=int(os.getenv("WNBA_PICK_SCAN_LIMIT", "5000")))
    if not picks:
        safe_json_write(OUT, [])
        log("WNBA results: no pending picks")
        return
    by_date = {}
    for p in picks:
        d = _pick_date(p)
        for dd in (d - timedelta(days=1), d, d + timedelta(days=1)):
            by_date.setdefault(dd.strftime("%Y%m%d"), []).append(p)
    event_players = {}
    # Historical debt can span months. Five scoreboard dates per run was too
    # small and repeatedly revisited dates whose legacy picks did not correspond
    # to an actual game. Process a bounded but useful backlog batch instead.
    max_dates = max(1, int(os.getenv("WNBA_RESULTS_MAX_DATES", "18")))
    max_events = max(1, int(os.getenv("WNBA_RESULT_GAME_CAP", "48")))
    today = datetime.now(timezone.utc).date()
    def _date_priority(item):
        ymd, _ = item
        try:
            d = datetime.strptime(ymd, "%Y%m%d").date()
        except Exception:
            return (9, 9999, ymd)
        # Drain historical settlement debt deterministically: completed old
        # pending dates first.  The previous "recent first" ordering starved old
        # WNBA picks forever because every run was capped to only a few dates.
        # Future windows remain last.
        return (0 if d <= today else 1, d.toordinal() if d <= today else abs((d - today).days), d.toordinal())

    for ymd, ps in sorted(by_date.items(), key=_date_priority)[:max_dates]:
        for ev in espn_scoreboard(ymd):
            eid = str(ev.get("id") or "")
            if not eid or not _event_final(ev):
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
        try:
            rows.extend(espn_summary_players(eid, names))
        except Exception as e:
            warn(f"WNBA summary failed {eid}: {e}")
    dedup = {}
    for r in rows:
        if r.get("normalized_name") and r.get("game_date"):
            dedup[(r["normalized_name"], r["game_date"])] = r
    rows = list(dedup.values())
    safe_json_write(OUT, rows)
    if rows:
        upsert_rows("prop_hunter_player_gamelogs", rows, "sport,league,season,game_id,normalized_name")
    log(f"WNBA results done: pending={len(picks)} events={len(event_players)} rows={len(rows)}")

if __name__ == "__main__":
    main()
