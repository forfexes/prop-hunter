#!/usr/bin/env python3
"""PROP HUNTER — 365-day league-wide player gamelog backfill.

Idempotent historical importer for MLB, NBA, WNBA, NFL and NHL.
Uses public/official sources already accepted by the project and writes to
prop_hunter_player_gamelogs with the canonical conflict key.
"""
from __future__ import annotations
import os, re, time
from datetime import date, datetime, timedelta, timezone
from typing import Any
from prop_hunter_shared_utils import http_json, log, norm_name, to_float, upsert_rows, warn

DAYS=max(1,int(os.getenv("PH_BACKFILL_DAYS","365")))
CUTOFF=(datetime.now(timezone.utc).date()-timedelta(days=DAYS))
BATCH=max(100,int(os.getenv("PH_BACKFILL_FLUSH_ROWS","1500")))

def flush(rows):
    if rows:
        upsert_rows("prop_hunter_player_gamelogs",rows,"sport,league,season,game_id,normalized_name")
        log(f"backfill flush rows={len(rows)}")
        rows.clear()

def season_basketball(d):
    return f"{d.year if d.month>=9 else d.year-1}-{(d.year+1)%100:02d}" if d.month>=9 else f"{d.year-1}-{d.year%100:02d}"

def made(v):
    if v in (None,"","--"): return None
    s=str(v).strip()
    if re.fullmatch(r"\d+(?:\.\d+)?[-/]\d+(?:\.\d+)?",s): s=re.split(r"[-/]",s,1)[0]
    return to_float(s)

def espn_basketball(league):
    """League-wide ESPN scoreboard+summary. NBA/WNBA completed games only."""
    rows=[]; total=0
    endpoint="wnba" if league=="WNBA" else "nba"
    d=CUTOFF
    while d<=datetime.now(timezone.utc).date():
        ymd=d.strftime("%Y%m%d")
        events=(http_json(f"https://site.api.espn.com/apis/site/v2/sports/basketball/{endpoint}/scoreboard",
                          params={"dates":ymd,"limit":100},retries=1) or {}).get("events",[]) or []
        for ev in events:
            status=((ev.get("status") or {}).get("type") or {})
            if not status.get("completed"): continue
            gid=str(ev.get("id") or "")
            if not gid: continue
            data=http_json(f"https://site.api.espn.com/apis/site/v2/sports/basketball/{endpoint}/summary",
                           params={"event":gid},retries=1) or {}
            gd=str(((data.get("header") or {}).get("competitions") or [{}])[0].get("date") or "")[:10] or d.isoformat()
            for tb in ((data.get("boxscore") or {}).get("players") or []):
                team=((tb.get("team") or {}).get("abbreviation") or (tb.get("team") or {}).get("displayName"))
                for group in tb.get("statistics") or []:
                    labels=[str(x).upper() for x in (group.get("labels") or group.get("keys") or [])]
                    for ath in group.get("athletes") or []:
                        info=ath.get("athlete") or {}; name=info.get("displayName") or info.get("shortName")
                        if not name: continue
                        vals=ath.get("stats") or []; sm={labels[i]:vals[i] for i in range(min(len(labels),len(vals)))}
                        pts=to_float(sm.get("PTS"),0) or 0; reb=to_float(sm.get("REB"),0) or 0; ast=to_float(sm.get("AST"),0) or 0
                        rows.append({"sport":"BASKETBALL","league":league,"season":str(d.year) if league=="WNBA" else season_basketball(d),
                          "source":"espn_summary_backfill","source_game_id":gid,"game_id":gid,"game_date":gd,
                          "player_name":name,"normalized_name":norm_name(name),"team":team,
                          "minutes":to_float(sm.get("MIN")),"points":pts,"rebounds":reb,"assists":ast,
                          "pra":pts+reb+ast,"ra":reb+ast,"threes_made":made(sm.get("3PM") or sm.get("3PT")),
                          "steals":to_float(sm.get("STL")),"blocks":to_float(sm.get("BLK")),
                          "turnovers":to_float(sm.get("TO") or sm.get("TOV")),
                          "double_double":sum(1 for v in (pts,reb,ast) if v>=10)>=2,
                          "triple_double":sum(1 for v in (pts,reb,ast) if v>=10)>=3,
                          "raw":{"stat_map":sm,"athlete_id":info.get("id"),"backfill_days":DAYS}})
            total+=1
            if len(rows)>=BATCH: flush(rows)
        if events: log(f"{league} backfill {ymd}: games={len(events)} total_games={total}")
        d+=timedelta(days=1)
    flush(rows); return total

def mlb():
    rows=[]; games=0
    start=CUTOFF.isoformat(); end=datetime.now(timezone.utc).date().isoformat()
    data=http_json("https://statsapi.mlb.com/api/v1/schedule",
                   params={"sportId":1,"startDate":start,"endDate":end,"gameType":"R,F,D,L,W"},retries=2) or {}
    for block in data.get("dates") or []:
        gd=str(block.get("date") or "")[:10]
        for g in block.get("games") or []:
            if str((g.get("status") or {}).get("abstractGameState") or "").lower()!="final": continue
            gid=str(g.get("gamePk") or "")
            box=http_json(f"https://statsapi.mlb.com/api/v1/game/{gid}/boxscore",retries=2) or {}
            for side in ("away","home"):
                team=((box.get("teams") or {}).get(side) or {})
                tab=((team.get("team") or {}).get("abbreviation") or (team.get("team") or {}).get("name"))
                for p in (team.get("players") or {}).values():
                    person=p.get("person") or {}; name=person.get("fullName")
                    if not name: continue
                    st=p.get("stats") or {}; bat=st.get("batting") or {}; pit=st.get("pitching") or {}
                    if not bat and not pit: continue
                    row={"sport":"BASEBALL","league":"MLB","country":"USA","season":gd[:4],
                         "source":"mlb_statsapi_boxscore_backfill","source_game_id":gid,"game_id":gid,"game_date":gd,
                         "player_name":name,"normalized_name":norm_name(name),"team":tab,
                         "raw":{"person_id":person.get("id"),"backfill_days":DAYS}}
                    if bat:
                        row.update({"hits":to_float(bat.get("hits")),"doubles":to_float(bat.get("doubles")),
                         "triples":to_float(bat.get("triples")),"total_bases":to_float(bat.get("totalBases")),
                         "home_runs":to_float(bat.get("homeRuns")),"rbi":to_float(bat.get("rbi")),
                         "runs":to_float(bat.get("runs")),"strikeouts_batter":to_float(bat.get("strikeOuts")),
                         "walks_batter":to_float(bat.get("baseOnBalls")),"stolen_bases":to_float(bat.get("stolenBases"))})
                    if pit:
                        row.update({"pitcher_strikeouts":to_float(pit.get("strikeOuts")),
                         "pitcher_innings":to_float(pit.get("inningsPitched")),"pitcher_hits_allowed":to_float(pit.get("hits")),
                         "pitcher_earned_runs":to_float(pit.get("earnedRuns")),"pitcher_walks":to_float(pit.get("baseOnBalls")),
                         "pitcher_home_runs_allowed":to_float(pit.get("homeRuns"))})
                    rows.append(row)
            games+=1
            if len(rows)>=BATCH: flush(rows)
        if block.get("games"): log(f"MLB backfill {gd}: games={len(block.get('games') or [])} total_final={games}")
    flush(rows); return games

def nfl():
    try:
        import nflreadpy as nfl
    except Exception as e:
        warn(f"NFL backfill unavailable: {e}"); return 0
    seasons=sorted({CUTOFF.year-1,CUTOFF.year,datetime.now(timezone.utc).year})
    try:
        df=nfl.load_player_stats(seasons=seasons)
        try: df=df.to_pandas()
        except Exception: pass
        sdf=nfl.load_schedules(seasons=seasons)
        try: sdf=sdf.to_pandas()
        except Exception: pass
    except Exception as e:
        warn(f"NFL backfill load failed: {e}"); return 0
    smap={}
    for _,g in sdf.iterrows():
        gd=str(g.get("gameday") or g.get("game_date") or "")[:10]
        if not gd or gd<CUTOFF.isoformat(): continue
        for team,opp in ((str(g.get("away_team") or ""),str(g.get("home_team") or "")),
                         (str(g.get("home_team") or ""),str(g.get("away_team") or ""))):
            smap[(str(g.get("season") or ""),str(g.get("week") or ""),team)]=(str(g.get("game_id") or g.get("old_game_id") or ""),gd,opp)
    rows=[]
    for _,r in df.iterrows():
        season=str(r.get("season") or ""); week=str(r.get("week") or ""); team=str(r.get("recent_team") or r.get("team") or "")
        meta=smap.get((season,week,team))
        if not meta: continue
        gid,gd,opp=meta; name=r.get("player_display_name") or r.get("player_name") or r.get("name")
        if not name: continue
        rush=to_float(r.get("rushing_tds"),0) or 0; rec=to_float(r.get("receiving_tds"),0) or 0
        td=rush+rec
        rows.append({"sport":"AMERICAN_FOOTBALL","league":"NFL","season":season,"week":week,
          "source":"nflreadpy_backfill","source_game_id":gid,"game_id":gid,"game_date":gd,
          "player_name":name,"normalized_name":norm_name(name),"team":team,"opponent":opp,
          "receptions":to_float(r.get("receptions")),"receiving_yards":to_float(r.get("receiving_yards")),
          "rushing_yards":to_float(r.get("rushing_yards")),"rushing_attempts":to_float(r.get("carries")),
          "passing_yards":to_float(r.get("passing_yards")),"passing_touchdowns":to_float(r.get("passing_tds")),
          "interceptions":to_float(r.get("interceptions")),"receiving_touchdowns":rec,"rushing_touchdowns":rush,
          "touchdowns":td,"anytime_td":1.0 if td>=1 else 0.0,"two_plus_td":1.0 if td>=2 else 0.0,
          "three_plus_td":1.0 if td>=3 else 0.0,"targets":to_float(r.get("targets")),
          "raw":{"backfill_days":DAYS}})
        if len(rows)>=BATCH: flush(rows)
    n=len(rows); flush(rows); return len(smap)//2

def nhl():
    """Official NHL schedule + boxscore, league-wide."""
    rows=[]; games=0; seen=set()
    d=CUTOFF
    while d<=datetime.now(timezone.utc).date():
        data=http_json(f"https://api-web.nhle.com/v1/schedule/{d.isoformat()}",retries=1) or {}
        for week in data.get("gameWeek") or []:
            for g in week.get("games") or []:
                gid=str(g.get("id") or "")
                if not gid or gid in seen or str(g.get("gameState") or "") not in ("OFF","FINAL"): continue
                seen.add(gid)
                box=http_json(f"https://api-web.nhle.com/v1/gamecenter/{gid}/boxscore",retries=1) or {}
                gd=str(box.get("gameDate") or g.get("gameDate") or d.isoformat())[:10]
                for side in ("awayTeam","homeTeam"):
                    team=box.get(side) or {}; tab=team.get("abbrev") or team.get("commonName")
                    for bucket in ("forwards","defense","goalies"):
                        for p in ((box.get("playerByGameStats") or {}).get(side) or {}).get(bucket,[]) or []:
                            name=p.get("name")
                            if isinstance(name,dict): name=name.get("default")
                            if not name: continue
                            goals=to_float(p.get("goals"),0) or 0; assists=to_float(p.get("assists"),0) or 0
                            rows.append({"sport":"NHL","league":"NHL","season":str(box.get("season") or ""),
                              "source":"nhl_official_boxscore_backfill","source_game_id":gid,"game_id":gid,"game_date":gd,
                              "player_name":name,"normalized_name":norm_name(name),"team":tab,
                              "goals":goals,"assists_hockey":assists,"hockey_points":goals+assists,
                              "shots_on_goal":to_float(p.get("sog")),"goalie_saves":to_float(p.get("saves")),
                              "blocked_shots":to_float(p.get("blockedShots")),"power_play_points":to_float(p.get("powerPlayPoints")),
                              "toi":p.get("toi"),"raw":{"player_id":p.get("playerId"),"backfill_days":DAYS}})
                games+=1
                if len(rows)>=BATCH: flush(rows)
        d+=timedelta(days=7)
        if games: log(f"NHL backfill through {min(d,datetime.now(timezone.utc).date())}: total_games={games}")
    flush(rows); return games

def main():
    sports=[x.strip().upper() for x in os.getenv("PH_BACKFILL_SPORTS","MLB,NBA,WNBA,NFL,NHL").split(",") if x.strip()]
    log(f"365d backfill start cutoff={CUTOFF} sports={','.join(sports)}")
    counts={}
    if "NFL" in sports: counts["NFL"]=nfl()
    if "MLB" in sports: counts["MLB"]=mlb()
    if "NBA" in sports: counts["NBA"]=espn_basketball("NBA")
    if "WNBA" in sports: counts["WNBA"]=espn_basketball("WNBA")
    if "NHL" in sports: counts["NHL"]=nhl()
    log("365d backfill done "+", ".join(f"{k} games={v}" for k,v in counts.items()))

if __name__=="__main__":
    main()
