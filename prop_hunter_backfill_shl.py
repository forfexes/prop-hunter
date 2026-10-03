#!/usr/bin/env python3
"""Bounded SHL player-game backfill from public Statnet PlayerReport PDFs.

The public reports expose one per-game table for skaters and goalkeepers.
Initial mode crawls current + previous calendar year and keeps at most the
newest 40 games per player. Incremental mode checks only recent dates.
"""
from __future__ import annotations

import os
import re
import time
import urllib3
from collections import Counter, deque
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Any, Dict, Iterable, List, Tuple
from urllib.parse import parse_qs, urljoin, urlparse

import pdfplumber
import requests

from prop_hunter_shared_utils import log, norm_name, select_rows, to_float, upsert_rows

BASE = "https://reports.statnet.se/shl/"
LEAGUE = "SHL"
SPORT = "ICE_HOCKEY"
KEEP = max(30, min(40, int(os.getenv("PH_SHL_LAST_N", "40"))))
FULL_EVENT_CAP = max(150, min(400, int(os.getenv("PH_SHL_MAX_EVENTS", "320"))))
INCREMENTAL_DAYS = max(2, min(14, int(os.getenv("PH_SHL_INCREMENTAL_DAYS", "7"))))
INCREMENTAL_EVENT_CAP = max(10, min(100, int(os.getenv("PH_SHL_INCREMENTAL_MAX_EVENTS", "50"))))
INITIAL_COMPLETE_ROWS = max(2500, int(os.getenv("PH_SHL_INITIAL_COMPLETE_ROWS", "4500")))
TIMEOUT = max(5, min(30, int(os.getenv("PH_SHL_TIMEOUT", "15"))))
COOLDOWN = max(0.02, min(0.5, float(os.getenv("PH_SHL_COOLDOWN", "0.06"))))
BATCH = max(100, min(1000, int(os.getenv("PH_SHL_BATCH", "500"))))
HEADERS = {"Accept": "text/html,application/pdf,*/*", "User-Agent": "PROP-HUNTER/shl-data"}

# Statnet currently serves an incomplete certificate chain on GitHub runners.
# This bypass is deliberately scoped to the single hard-coded public read-only
# host above and is never used by other PROP HUNTER sources.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _get(url: str) -> requests.Response | None:
    if not str(url).startswith(BASE):
        return None
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, verify=False)
        if r.status_code in {401, 403, 404, 429}:
            log(f"SHL Statnet HTTP {r.status_code} {url}")
            return None
        r.raise_for_status()
        time.sleep(COOLDOWN)
        return r
    except Exception as exc:
        log(f"SHL Statnet request failed: {type(exc).__name__}: {exc}")
        return None


def existing_rows() -> List[Dict[str, Any]]:
    return select_rows(
        "prop_hunter_player_gamelogs",
        limit=None,
        filters={"league": LEAGUE},
        order_by="id",
    )


def _hrefs(html: str) -> List[str]:
    return re.findall(r'href=["\']([^"\']+)["\']', str(html or ""), flags=re.I)


def _day_value(href: str) -> str:
    try:
        return str(parse_qs(urlparse(urljoin(BASE, href)).query).get("day", [""])[0])
    except Exception:
        return ""


def _game_value(href: str) -> str:
    try:
        return str(parse_qs(urlparse(urljoin(BASE, href)).query).get("game", [""])[0])
    except Exception:
        return ""


def discover_full_games() -> List[Tuple[str, str]]:
    now = datetime.now(timezone.utc).date()
    years = {str(now.year), str(now.year - 1)}
    queue = deque(f"Default.aspx?day={y}" for y in sorted(years, reverse=True))
    seen_pages = set()
    games = set()

    while queue:
        rel = queue.popleft()
        url = urljoin(BASE, rel)
        if url in seen_pages:
            continue
        seen_pages.add(url)
        r = _get(url)
        if r is None:
            continue
        for href in _hrefs(r.text):
            day = _day_value(href)
            game = _game_value(href)
            if not day or day[:4] not in years:
                continue
            if len(day) == 8 and game:
                try:
                    d = datetime.strptime(day, "%Y%m%d").date()
                except Exception:
                    continue
                if d < now:
                    games.add((day, game))
                continue
            if len(day) in {4, 6, 8}:
                queue.append(href)
    out = sorted(games, reverse=True)
    log(f"SHL discovery pages={len(seen_pages)} games={len(out)}")
    return out


def discover_recent_games(days: int = INCREMENTAL_DAYS) -> List[Tuple[str, str]]:
    now = datetime.now(timezone.utc).date()
    games = set()
    for offset in range(1, days + 1):
        day = (now - timedelta(days=offset)).strftime("%Y%m%d")
        r = _get(urljoin(BASE, f"Default.aspx?day={day}"))
        if r is None:
            continue
        for href in _hrefs(r.text):
            hday = _day_value(href)
            game = _game_value(href)
            if hday == day and game:
                games.add((day, game))
    return sorted(games, reverse=True)


def report_url(day: str, game: str) -> str:
    return urljoin(BASE, f"reports/{day}-{game}-PlayerReport.pdf")


def _minutes(value: Any) -> float | None:
    s = str(value or "").strip()
    if not s:
        return None
    if ":" in s:
        try:
            mm, ss = s.split(":", 1)
            return round(int(mm) + int(ss) / 60.0, 4)
        except Exception:
            return None
    return to_float(s)


def _num(value: Any, zero_blank: bool = False) -> float | None:
    if value in (None, ""):
        return 0.0 if zero_blank else None
    s = str(value).strip().replace("+", "")
    if s.endswith("%"):
        s = s[:-1]
    return to_float(s, 0.0 if zero_blank else None)


def _player_name(cell: Any) -> str:
    s = str(cell or "").strip()
    return re.sub(r"^\s*\d+\s*", "", s).strip()


def _season(day: str) -> str:
    d = datetime.strptime(day, "%Y%m%d").date()
    start = d.year if d.month >= 8 else d.year - 1
    return f"{start}-{(start + 1) % 100:02d}"


def parse_tables(tables: Iterable[List[List[Any]]], day: str, game: str) -> List[Dict[str, Any]]:
    teams = [x.strip() for x in str(game).split("-", 1)]
    while len(teams) < 2:
        teams.append("")
    rows: List[Dict[str, Any]] = []
    player_table_count = 0
    current_team_index = 0
    game_id = f"SHL_{day}_{game}"
    season = _season(day)

    for table in tables:
        if not table or not table[0]:
            continue
        header = [str(x or "").strip() for x in table[0]]
        kind = header[0].lower()
        if kind == "player":
            current_team_index = min(player_table_count, 1)
            player_table_count += 1
            for row in table[1:]:
                if not row or not row[0]:
                    continue
                name = _player_name(row[0])
                toi = _minutes(row[12] if len(row) > 12 else None)
                if not name or toi is None or toi <= 0:
                    continue
                vals = list(row) + [""] * max(0, 13 - len(row))
                goals = _num(vals[2], True) or 0.0
                assists = _num(vals[3], True) or 0.0
                points = _num(vals[4], True)
                if points is None:
                    points = goals + assists
                team = teams[current_team_index]
                opp = teams[1 - current_team_index]
                rows.append({
                    "sport": SPORT, "league": LEAGUE, "country": "SE", "season": season,
                    "source": "shl_statnet_playerreport", "source_game_id": game_id,
                    "game_id": game_id, "game_date": f"{day[:4]}-{day[4:6]}-{day[6:8]}",
                    "player_name": name, "normalized_name": norm_name(name),
                    "team": team or None, "opponent": opp or None, "minutes": toi,
                    "goals": goals, "assists_hockey": assists, "hockey_points": points,
                    "shots_on_goal": _num(vals[1], True),
                    "blocked_shots": _num(vals[8], True),
                    "raw": {
                        "jersey_player": vals[0], "plus_minus": vals[5], "pim": _num(vals[6], True),
                        "hits": _num(vals[7], True), "blocks": _num(vals[8], True),
                        "faceoffs": vals[9], "faceoff_pct": vals[10], "shifts": _num(vals[11], True),
                        "report_url": report_url(day, game),
                    },
                })
        elif kind == "goalkeeper":
            team_index = min(max(player_table_count - 1, 0), 1)
            for row in table[1:]:
                if not row or not row[0]:
                    continue
                vals = list(row) + [""] * max(0, 10 - len(row))
                name = _player_name(vals[0])
                toi = _minutes(vals[9])
                if not name or toi is None or toi <= 0:
                    continue
                team = teams[team_index]
                opp = teams[1 - team_index]
                rows.append({
                    "sport": SPORT, "league": LEAGUE, "country": "SE", "season": season,
                    "source": "shl_statnet_playerreport", "source_game_id": game_id,
                    "game_id": game_id, "game_date": f"{day[:4]}-{day[4:6]}-{day[6:8]}",
                    "player_name": name, "normalized_name": norm_name(name),
                    "team": team or None, "opponent": opp or None, "minutes": toi,
                    "goalie_saves": _num(vals[1], True),
                    "raw": {
                        "jersey_player": vals[0], "goals_against": _num(vals[2], True),
                        "shots_without_attempt": _num(vals[3], True), "save_pct": vals[4],
                        "pp_save_pct": vals[5], "eq_save_pct": vals[6],
                        "shutout": bool(str(vals[7] or "").strip()), "pim": _num(vals[8], True),
                        "report_url": report_url(day, game),
                    },
                })
    return rows


def fetch_game(day: str, game: str) -> List[Dict[str, Any]]:
    r = _get(report_url(day, game))
    if r is None or not r.content.startswith(b"%PDF"):
        return []
    try:
        tables: List[List[List[Any]]] = []
        with pdfplumber.open(BytesIO(r.content)) as pdf:
            for page in pdf.pages:
                tables.extend(page.extract_tables() or [])
        return parse_tables(tables, day, game)
    except Exception as exc:
        log(f"SHL PDF parse failed {day} {game}: {type(exc).__name__}: {exc}")
        return []


def main() -> None:
    existing = existing_rows()
    full_mode = len(existing) < INITIAL_COMPLETE_ROWS
    games = discover_full_games() if full_mode else discover_recent_games()
    cap = FULL_EVENT_CAP if full_mode else INCREMENTAL_EVENT_CAP
    games = games[:cap]
    counts: Counter = Counter()
    if full_mode:
        for row in existing:
            nk = str(row.get("normalized_name") or "")
            if nk:
                counts[nk] += 1

    log(f"SHL backfill mode={'full' if full_mode else 'incremental'} existing={len(existing)} games={len(games)} cap={cap}")
    pending: List[Dict[str, Any]] = []
    processed = written = 0
    for day, game in games:
        rows = fetch_game(day, game)
        if not rows:
            continue
        processed += 1
        for row in rows:
            nk = str(row.get("normalized_name") or "")
            if full_mode and counts.get(nk, 0) >= KEEP:
                continue
            pending.append(row)
            if full_mode:
                counts[nk] += 1
        if len(pending) >= BATCH:
            upsert_rows("prop_hunter_player_gamelogs", pending, "sport,league,season,game_id,normalized_name")
            written += len(pending)
            pending.clear()
        if processed % 25 == 0:
            log(f"SHL backfill progress={processed}/{len(games)} written={written}")

    if pending:
        upsert_rows("prop_hunter_player_gamelogs", pending, "sport,league,season,game_id,normalized_name")
        written += len(pending)
    log(f"SHL backfill done processed_games={processed} written_rows={written}")


if __name__ == "__main__":
    main()
