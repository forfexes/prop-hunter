#!/usr/bin/env python3
"""Backfill up to the last 40 NBA G League games per player."""
from __future__ import annotations

import os
from typing import Any, Dict, List

from prop_hunter_shared_utils import http_json, log, norm_name, to_float, upsert_rows

LEAGUE = "NBA_G_LEAGUE"
SPORT = "BASKETBALL"
KEEP = max(30, min(40, int(os.getenv("PH_GLEAGUE_LAST_N", "40"))))
BATCH = max(100, min(1000, int(os.getenv("PH_GLEAGUE_BATCH", "500"))))


def _season_candidates() -> List[str]:
    explicit = str(os.getenv("PH_GLEAGUE_SEASONS", "")).strip()
    if explicit:
        return [x.strip() for x in explicit.split(",") if x.strip()]
    return ["2026-27", "2025-26"]


def _row(record: Dict[str, Any], season: str) -> Dict[str, Any] | None:
    name = str(record.get("PLAYER_NAME") or "").strip()
    gid = str(record.get("GAME_ID") or "").strip()
    if not name or not gid:
        return None
    pts = to_float(record.get("PTS"), 0.0) or 0.0
    reb = to_float(record.get("REB"), 0.0) or 0.0
    ast = to_float(record.get("AST"), 0.0) or 0.0
    matchup = str(record.get("MATCHUP") or "")
    opponent = ""
    if " vs. " in matchup:
        opponent = matchup.split(" vs. ", 1)[1].strip()
    elif " @ " in matchup:
        opponent = matchup.split(" @ ", 1)[1].strip()
    return {
        "sport": SPORT,
        "league": LEAGUE,
        "season": str(record.get("SEASON_YEAR") or season),
        "source": "nba_stats_gleague",
        "source_game_id": gid,
        "game_id": gid,
        "game_date": str(record.get("GAME_DATE") or "")[:10],
        "player_name": name,
        "normalized_name": norm_name(name),
        "team": record.get("TEAM_ABBREVIATION") or record.get("TEAM_NAME"),
        "opponent": opponent or None,
        "minutes": to_float(record.get("MIN")),
        "points": pts,
        "rebounds": reb,
        "assists": ast,
        "pra": pts + reb + ast,
        "ra": reb + ast,
        "pa": pts + ast,
        "pr": pts + reb,
        "threes_made": to_float(record.get("FG3M")),
        "steals": to_float(record.get("STL")),
        "blocks": to_float(record.get("BLK")),
        "turnovers": to_float(record.get("TOV")),
        "double_double": bool((to_float(record.get("DD2"), 0) or 0) >= 1),
        "triple_double": bool((to_float(record.get("TD3"), 0) or 0) >= 1),
        "raw": {
            "player_id": record.get("PLAYER_ID"),
            "team_id": record.get("TEAM_ID"),
            "matchup": matchup,
            "wl": record.get("WL"),
            "fgm": record.get("FGM"),
            "fga": record.get("FGA"),
            "fg3a": record.get("FG3A"),
            "ftm": record.get("FTM"),
            "fta": record.get("FTA"),
            "oreb": record.get("OREB"),
            "dreb": record.get("DREB"),
            "pf": record.get("PF"),
            "plus_minus": record.get("PLUS_MINUS"),
            "fantasy_points": record.get("NBA_FANTASY_PTS"),
            "last_n_requested": KEEP,
        },
    }



def _made(v: Any):
    if v in (None, "", "--"):
        return None
    text = str(v).strip()
    if "-" in text or "/" in text:
        for sep in ("-", "/"):
            if sep in text:
                text = text.split(sep, 1)[0]
                break
    return to_float(text)


def _season_basketball(date_text: str) -> str:
    try:
        year, month = [int(x) for x in str(date_text)[:7].split("-")]
    except Exception:
        return "2025-26"
    start = year if month >= 9 else year - 1
    return f"{start}-{(start + 1) % 100:02d}"


def fetch_espn() -> List[Dict[str, Any]]:
    """Fetch G League boxscores from ESPN, newest useful season only."""
    base = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba-g-league"
    date_range = os.getenv("PH_GLEAGUE_ESPN_DATES", "20260101-20260415")
    payload = http_json(
        f"{base}/scoreboard",
        params={"dates": date_range, "limit": 1000},
        retries=1,
    ) or {}
    events = list(payload.get("events") or [])
    log(f"G League ESPN scoreboard range={date_range} events={len(events)}")
    if not events:
        return []

    # Newest games first lets us cap to 40/player without retaining old rows.
    events.sort(key=lambda e: str(e.get("date") or ""), reverse=True)
    out: List[Dict[str, Any]] = []
    counts: Dict[str, int] = {}
    completed = 0

    for ev in events:
        status = ((ev.get("status") or {}).get("type") or {})
        if not status.get("completed"):
            continue
        gid = str(ev.get("id") or "")
        if not gid:
            continue
        data = http_json(f"{base}/summary", params={"event": gid}, retries=0) or {}
        boxes = ((data.get("boxscore") or {}).get("players") or [])
        if not boxes:
            continue
        header_comp = ((data.get("header") or {}).get("competitions") or [{}])[0]
        gd = str(header_comp.get("date") or ev.get("date") or "")[:10]
        season = _season_basketball(gd)
        completed += 1

        for tb in boxes:
            team_obj = tb.get("team") or {}
            team = team_obj.get("abbreviation") or team_obj.get("displayName")
            for group in tb.get("statistics") or []:
                labels = [str(x).upper() for x in (group.get("labels") or group.get("keys") or [])]
                for ath in group.get("athletes") or []:
                    info = ath.get("athlete") or {}
                    name = info.get("displayName") or info.get("shortName")
                    if not name:
                        continue
                    nk = norm_name(name)
                    if counts.get(nk, 0) >= KEEP:
                        continue
                    vals = ath.get("stats") or []
                    sm = {labels[i]: vals[i] for i in range(min(len(labels), len(vals)))}
                    pts = to_float(sm.get("PTS"), 0) or 0
                    reb = to_float(sm.get("REB"), 0) or 0
                    ast = to_float(sm.get("AST"), 0) or 0
                    out.append({
                        "sport": SPORT,
                        "league": LEAGUE,
                        "season": season,
                        "source": "espn_gleague_summary",
                        "source_game_id": gid,
                        "game_id": gid,
                        "game_date": gd,
                        "player_name": name,
                        "normalized_name": nk,
                        "team": team,
                        "minutes": to_float(sm.get("MIN")),
                        "points": pts,
                        "rebounds": reb,
                        "assists": ast,
                        "pra": pts + reb + ast,
                        "ra": reb + ast,
                        "pa": pts + ast,
                        "pr": pts + reb,
                        "threes_made": _made(sm.get("3PM") or sm.get("3PT")),
                        "steals": to_float(sm.get("STL")),
                        "blocks": to_float(sm.get("BLK")),
                        "turnovers": to_float(sm.get("TO") or sm.get("TOV")),
                        "double_double": sum(1 for v in (pts, reb, ast) if v >= 10) >= 2,
                        "triple_double": sum(1 for v in (pts, reb, ast) if v >= 10) >= 3,
                        "raw": {
                            "athlete_id": info.get("id"),
                            "stat_map": sm,
                            "espn_event_date": ev.get("date"),
                            "last_n_requested": KEEP,
                        },
                    })
                    counts[nk] = counts.get(nk, 0) + 1

    log(f"G League ESPN completed_games={completed} rows={len(out)} players={len(counts)}")
    return out

def fetch_season(season: str) -> List[Dict[str, Any]]:
    from nba_api.stats.endpoints import playergamelogs
    ep = playergamelogs.PlayerGameLogs(
        league_id_nullable="20",
        season_nullable=season,
        season_type_nullable="Regular Season",
        last_n_games_nullable=KEEP,
        timeout=45,
    )
    frames = ep.get_data_frames()
    if not frames:
        return []
    df = frames[0]
    if df is None or df.empty:
        return []
    rows = []
    for record in df.to_dict("records"):
        item = _row(record, season)
        if item:
            rows.append(item)
    return rows


def main() -> None:
    rows: List[Dict[str, Any]] = []
    used_season = "espn"
    errors = []

    try:
        rows = fetch_espn()
    except Exception as exc:
        errors.append(f"espn:{type(exc).__name__}:{exc}")
        log(f"G League ESPN fetch failed: {type(exc).__name__}: {exc}")

    # stats.nba.com is a fallback only; GitHub-hosted runners often time out.
    if not rows and str(os.getenv("PH_GLEAGUE_NBA_API_FALLBACK", "0")).lower() in {"1","true","yes","on"}:
        for season in _season_candidates():
            try:
                candidate = fetch_season(season)
            except Exception as exc:
                errors.append(f"{season}:{type(exc).__name__}:{exc}")
                log(f"G League {season} fetch failed: {type(exc).__name__}: {exc}")
                continue
            log(f"G League {season}: rows={len(candidate)}")
            if candidate:
                rows = candidate
                used_season = season
                break

    if not rows:
        log(f"G League backfill empty errors={errors[:2]}")
        return

    dedup = {}
    for row in rows:
        key = (
            row.get("sport"), row.get("league"), row.get("season"),
            row.get("game_id"), row.get("normalized_name"),
        )
        dedup[key] = row
    rows = list(dedup.values())

    for start in range(0, len(rows), BATCH):
        upsert_rows(
            "prop_hunter_player_gamelogs",
            rows[start:start + BATCH],
            "sport,league,season,game_id,normalized_name",
        )
    players = len({r.get("normalized_name") for r in rows})
    games = len({r.get("game_id") for r in rows})
    log(f"G League backfill done season={used_season} rows={len(rows)} players={players} games={games}")


if __name__ == "__main__":
    main()
