#!/usr/bin/env python3
"""Bounded Swiss National League player-game collector from public SIHF CSV exports.

The league schedule yields game ids. Each completed game exposes four public
CSV exports (home/away skaters + goalies). Only completed games returning valid
CSV are persisted. The global retention job caps history at 40 games/player.
"""
from __future__ import annotations

import csv
import io
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple
from urllib.parse import urljoin

import requests

from prop_hunter_shared_utils import log, norm_name, select_rows, to_float, upsert_rows

BASE="https://www.sihf.ch"
SCHEDULE=f"{BASE}/de/game-center/liga/spielplan/1-1"
GAME_STATS=f"{BASE}/de/game-center/game/spielerstatistik/{{game_id}}"
EXPORT=f"{BASE}/umbraco/GameCenter/GameDetail/ExportGamePlayerStats"
SCHEDULE_EXPORT=f"{BASE}/umbraco/GameCenter/League/ExportSchedule"
LEAGUE="SWISS_NL"
SPORT="ICE_HOCKEY"
KEEP=max(30,min(40,int(os.getenv("PH_SWISS_NL_LAST_N","40"))))
MAX_GAMES=max(80,min(420,int(os.getenv("PH_SWISS_NL_MAX_GAMES","340"))))
TIMEOUT=max(5,min(30,int(os.getenv("PH_SWISS_NL_TIMEOUT","15"))))
COOLDOWN=max(0.02,min(0.5,float(os.getenv("PH_SWISS_NL_COOLDOWN","0.06"))))
BATCH=max(100,min(1000,int(os.getenv("PH_SWISS_NL_BATCH","500"))))
HEADERS={"User-Agent":"PROP-HUNTER/swiss-nl-data","Accept":"text/html,text/csv,*/*"}

SKATER_ALIASES=("gamePlayerStatsHome","gamePlayerStatsAway")
GOALIE_ALIASES=("gameGoalieStatsHome","gameGoalieStatsAway")
GAME_META: Dict[str,Dict[str,str]]={}


def _session() -> requests.Session:
    s=requests.Session()
    s.headers.update(HEADERS)
    return s


def _minutes(value: Any) -> float | None:
    text=str(value or "").strip()
    if not text:
        return None
    if ":" in text:
        try:
            m,s=text.split(":",1)
            return round(int(m)+int(s)/60.0,4)
        except Exception:
            return None
    return to_float(text)


def _display_name(raw: Any) -> str:
    # SIHF CSV uses "Surname Givenname". Move the final given-name token first:
    # "von Rohr Manuel" -> "Manuel von Rohr".
    parts=[p for p in str(raw or "").strip().split() if p]
    if len(parts)>=2:
        return " ".join([parts[-1],*parts[:-1]])
    return " ".join(parts)


def _float(row: Dict[str,str], key: str, default: float | None=None) -> float | None:
    value=row.get(key)
    if value in (None,"","-"):
        return default
    return to_float(str(value).replace("%",""),default)


def _date_from_html(html: str) -> str | None:
    patterns=(
        r'datetime=["\'](20\d{2}-\d{2}-\d{2})',
        r'"date"\s*:\s*"(20\d{2}-\d{2}-\d{2})',
        r'(20\d{2}-\d{2}-\d{2})[T ]\d{2}:\d{2}',
        r'(?<!\d)(\d{2})\.(\d{2})\.(20\d{2})(?!\d)',
    )
    for idx,pat in enumerate(patterns):
        m=re.search(pat,html,re.I)
        if not m:
            continue
        if idx==3:
            return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
        return m.group(1)
    return None


def _season(game_id: str, game_date: str | None) -> str:
    if game_date:
        try:
            d=datetime.fromisoformat(game_date).date()
            start=d.year if d.month>=8 else d.year-1
            return f"{start}-{(start+1)%100:02d}"
        except Exception:
            pass
    try:
        end=int(str(game_id)[:4])
        return f"{end-1}-{end%100:02d}"
    except Exception:
        return ""


def schedule_game_ids(session: requests.Session) -> List[str]:
    """Return newest completed official Swiss NL games from schedule CSV."""
    now=datetime.now(timezone.utc)
    today=now.date()
    current_season=now.year+1 if now.month>=7 else now.year
    season_ids=(current_season,current_season-1)
    pairs=[]

    for season_id in season_ids:
        r=session.get(
            SCHEDULE_EXPORT,
            params={"leagueId":"1","regionId":"1","format":"Csv","season":str(season_id)},
            headers={"Referer":f"{SCHEDULE}?season={season_id}","Accept":"text/csv,*/*"},
            timeout=TIMEOUT,
        )
        if r.status_code!=200 or "csv" not in str(r.headers.get("content-type") or "").lower():
            log(f"Swiss NL schedule export failed season={season_id} status={r.status_code}")
            continue
        text=r.content.decode("utf-8-sig",errors="replace")
        for record in csv.DictReader(io.StringIO(text),delimiter=";"):
            gid=str(record.get("Id") or "").strip()
            if not re.fullmatch(r"\d{14}",gid):
                continue
            if str(record.get("Liga") or "").strip().upper()!="NL":
                continue
            status=str(record.get("Status") or "").strip().lower()
            if status not in {"ende","final","finished"}:
                continue
            phase=str(record.get("Phase") or "").strip()
            phase_l=phase.lower()
            if not phase or phase=="---" or "exhibition" in phase_l:
                continue
            try:
                d=datetime.strptime(str(record.get("Datum") or "").strip(),"%d.%m.%Y").date()
            except Exception:
                continue
            if d>=today:
                continue
            GAME_META[gid]={
                "date":d.isoformat(),
                "home":str(record.get("Home") or "").strip(),
                "away":str(record.get("Away") or "").strip(),
                "phase":phase,
            }
            pairs.append((d,gid))

    seen=set()
    out=[]
    for _date,gid in sorted(pairs,reverse=True):
        if gid in seen:
            continue
        seen.add(gid)
        out.append(gid)
    log(f"Swiss NL schedule export seasons={season_ids} completed_official={len(out)}")
    return out[:MAX_GAMES]


def _csv_rows(session: requests.Session, game_url: str, game_id: str, alias: str) -> List[Dict[str,str]]:
    r=session.get(
        EXPORT,
        params={"gameId":game_id,"format":"Csv","alias":alias},
        headers={"Referer":game_url,"Accept":"text/csv,*/*"},
        timeout=TIMEOUT,
    )
    time.sleep(COOLDOWN)
    if r.status_code!=200 or "csv" not in str(r.headers.get("content-type") or "").lower():
        return []
    text=r.content.decode("utf-8-sig",errors="replace")
    try:
        return [dict(x) for x in csv.DictReader(io.StringIO(text),delimiter=";")]
    except Exception:
        return []


def _skater_rows(records: List[Dict[str,str]],game_id: str,game_date: str | None,alias: str) -> List[Dict[str,Any]]:
    out=[]
    season=_season(game_id,game_date)
    for record in records:
        name=_display_name(record.get("Spieler"))
        toi=_minutes(record.get("TOI Total"))
        if not name or toi is None or toi<=0:
            continue
        goals=_float(record,"G",0.0) or 0.0
        assists=_float(record,"A",0.0) or 0.0
        points=_float(record,"PTS",goals+assists)
        meta=GAME_META.get(game_id,{})
        is_home=alias.endswith("Home")
        team=meta.get("home") if is_home else meta.get("away")
        opponent=meta.get("away") if is_home else meta.get("home")
        out.append({
            "sport":SPORT,"league":LEAGUE,"country":"CH","season":season,
            "source":"sihf_game_player_csv","source_game_id":game_id,"game_id":game_id,
            "game_date":game_date,"player_name":name,"normalized_name":norm_name(name),
            "team":team or None,"opponent":opponent or None,
            "minutes":toi,"goals":goals,"assists_hockey":assists,
            "hockey_points":points if points is not None else goals+assists,
            "shots_on_goal":_float(record,"SOG",0.0),
            "blocked_shots":_float(record,"BkS",0.0),
            "raw":{
                "side":"home" if alias.endswith("Home") else "away",
                "phase":meta.get("phase"),"sihf_name":record.get("Spieler"),"jersey":record.get("No"),
                "position":record.get("Pos"),"primary_assists":record.get("A1"),
                "secondary_assists":record.get("A2"),"pim":record.get("PIM Total"),
                "plus_minus":record.get("+/-"),"shots_missed":record.get("SHM Total"),
                "shots_post":record.get("SHP Total"),"faceoffs_won":record.get("FOW Total"),
                "faceoffs_lost":record.get("FOL Total"),"faceoff_pct":record.get("FO%"),
                "toi_pp":record.get("TOI PP"),"toi_pk":record.get("TOI PK"),
            },
        })
    return out


def _goalie_rows(records: List[Dict[str,str]],game_id: str,game_date: str | None,alias: str) -> List[Dict[str,Any]]:
    out=[]
    season=_season(game_id,game_date)
    for record in records:
        name=_display_name(record.get("Spieler"))
        toi=_minutes(record.get("MIP"))
        if not name or toi is None or toi<=0:
            continue
        meta=GAME_META.get(game_id,{})
        is_home=alias.endswith("Home")
        team=meta.get("home") if is_home else meta.get("away")
        opponent=meta.get("away") if is_home else meta.get("home")
        out.append({
            "sport":SPORT,"league":LEAGUE,"country":"CH","season":season,
            "source":"sihf_game_goalie_csv","source_game_id":game_id,"game_id":game_id,
            "game_date":game_date,"player_name":name,"normalized_name":norm_name(name),
            "team":team or None,"opponent":opponent or None,
            "minutes":toi,"goalie_saves":_float(record,"SVS",0.0),
            "raw":{
                "side":"home" if alias.endswith("Home") else "away",
                "phase":meta.get("phase"),"sihf_name":record.get("Spieler"),"jersey":record.get("No"),
                "goals_against":record.get("GA"),"shots_against":record.get("SA"),
                "save_pct":record.get("SVS%"),"gaa":record.get("GAA"),"pim":record.get("PIM"),
            },
        })
    return out


def fetch_game(session: requests.Session,game_id: str) -> List[Dict[str,Any]]:
    game_url=GAME_STATS.format(game_id=game_id)
    page=session.get(game_url,timeout=TIMEOUT)
    if page.status_code!=200:
        return []
    game_date=(GAME_META.get(game_id) or {}).get("date") or _date_from_html(page.text)
    rows=[]
    valid=False
    for alias in SKATER_ALIASES:
        records=_csv_rows(session,game_url,game_id,alias)
        if records:
            valid=True
            rows.extend(_skater_rows(records,game_id,game_date,alias))
    for alias in GOALIE_ALIASES:
        records=_csv_rows(session,game_url,game_id,alias)
        if records:
            valid=True
            rows.extend(_goalie_rows(records,game_id,game_date,alias))
    return rows if valid else []


def existing_game_ids() -> set[str]:
    rows=select_rows("prop_hunter_player_gamelogs",limit=None,filters={"league":LEAGUE},order_by="id")
    return {str(r.get("game_id") or "") for r in rows if r.get("game_id")}


def main() -> None:
    session=_session()
    games=schedule_game_ids(session)
    existing=existing_game_ids()
    games=[g for g in games if g not in existing]
    log(f"Swiss NL backfill schedule_games={len(games)} existing_games={len(existing)} max={MAX_GAMES}")
    pending=[]
    processed=written=0
    for gid in games:
        rows=fetch_game(session,gid)
        if not rows:
            continue
        processed+=1
        pending.extend(rows)
        if len(pending)>=BATCH:
            upsert_rows("prop_hunter_player_gamelogs",pending,"sport,league,season,game_id,normalized_name")
            written+=len(pending);pending.clear()
        if processed%10==0:
            log(f"Swiss NL backfill progress completed_games={processed} written={written}")
    if pending:
        upsert_rows("prop_hunter_player_gamelogs",pending,"sport,league,season,game_id,normalized_name")
        written+=len(pending)
    log(f"Swiss NL backfill done completed_games={processed} written_rows={written}")


if __name__=="__main__":
    main()
