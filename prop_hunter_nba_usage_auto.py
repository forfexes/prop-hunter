"""Bounded scheduled NBA usage backfill from official completed game IDs.

No Telegram, no synthetic rows, no model joins or paid endpoints. The existing
primary Supabase table accepts official game usage only. Re-run idempotently.
"""
import argparse
import collections
import datetime as dt
import json
import os
import re
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from prop_hunter_nba_usage import safe_fetch_game_usage
from prop_hunter_nba_usage_ingest import upsert_official_game_usage

SCHEDULE_URLS = (
    "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json",
    "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json",
)

def get_json(url, headers=None, timeout=15):
    request = Request(url, headers={"User-Agent":"Mozilla/5.0", **(headers or {})})
    with urlopen(request, timeout=timeout) as response:
        raw = response.read(20_000_001)
    if len(raw) > 20_000_000:
        raise ValueError("Response exceeds source size limit")
    return json.loads(raw)

def completed_games(payload, today, days=45):
    earliest = today - dt.timedelta(days=days)
    games = {}
    for block in payload.get("leagueSchedule", {}).get("gameDates", []):
        for game in block.get("games", []):
            gid = str(game.get("gameId") or "")
            # Regular season only, consistent with the season usage source.
            if not re.fullmatch(r"002[0-9]{7}", gid) or str(game.get("gameStatus")) != "3":
                continue
            raw = str(game.get("gameDateEst") or block.get("gameDate") or "")
            day = None
            for fmt, length in (("%Y-%m-%d",10), ("%m/%d/%Y",10)):
                try:
                    day = dt.datetime.strptime(raw[:length],fmt).date()
                    break
                except ValueError:
                    continue
            if day is None or not earliest <= day <= today:
                continue
            if gid in games and games[gid] != day:
                raise ValueError("Conflicting official game dates")
            games[gid] = day
    return sorted(games.items(),key=lambda item:(item[1],item[0]),reverse=True)

def discover(today, days, fetch=get_json):
    for url in SCHEDULE_URLS:
        try:
            payload=fetch(url)
            if not payload.get("leagueSchedule",{}).get("gameDates"):
                raise ValueError("Official schedule missing")
            return completed_games(payload,today,days)
        except Exception as exc:
            print("NBA schedule unavailable:",type(exc).__name__)
    raise RuntimeError("No accessible official NBA schedule")

def existing_counts(url, key, earliest, fetch=get_json):
    if urlparse(url).scheme != "https" or not key:
        raise ValueError("Secure Supabase credentials required")
    # Fixed ordering prevents repeats/omissions during pagination.
    headers={"apikey":key,"Authorization":"Bearer "+key}
    result=collections.Counter()
    offset=0
    while offset < 50000:
        query=urlencode({"select":"nba_game_id,nba_player_id","game_date":"gte."+str(earliest),
                         "order":"nba_game_id.asc,nba_player_id.asc","limit":1000,"offset":offset})
        page=fetch(url.rstrip("/")+"/rest/v1/prop_hunter_nba_game_usage?"+query,headers=headers)
        if not isinstance(page,list):
            raise ValueError("Invalid usage table response")
        result.update(str(row["nba_game_id"]) for row in page)
        if len(page)<1000:
            return result
        offset+=len(page)
    raise ValueError("Usage backfill exceeds configured read budget")

def collect(games, counts, *, url, key, today, max_games=24,
            fetch_game=safe_fetch_game_usage, upsert=upsert_official_game_usage):
    # Prioritize the latest two days; give the remaining budget to the oldest
    # missing games, so historical L15 coverage grows rather than starves.
    missing=[(g,d) for g,d in games if counts.get(g,0)<16]
    fresh=[(g,d) for g,d in missing if d>=today-dt.timedelta(days=2)]
    older=[(g,d) for g,d in reversed(missing) if d<today-dt.timedelta(days=2)]
    budget=max_games
    chosen=fresh[:max(1,budget//2)]
    chosen+=older[:budget-len(chosen)]
    chosen+=(fresh[len(chosen):] if not older else [])[:max(0,budget-len(chosen))]
    imported=0
    failures=0
    for gid,day in chosen:
        rows=fetch_game(gid,day.isoformat(),timeout=7)
        if not rows:
            failures+=1
            print("NBA usage unavailable:",gid)
            continue
        # Every observation must match the requested fixture/date.
        if any(r.get("game_id")!=gid or r.get("game_date")!=day.isoformat() for r in rows):
            raise ValueError("Official usage fixture mismatch")
        imported+=upsert(rows,url=url,service_key=key)
    summary={"completed_games":len(games),"attempted":len(chosen),
             "previous_games_with_16_plus_rows":sum(counts.get(g,0)>=16 for g,_ in games),
             "rows_upserted":imported,"unavailable_games":failures,
             "unattempted_incomplete_games":len(missing)-len(chosen)}
    print(json.dumps(summary,sort_keys=True))
    return summary

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--days",type=int,default=45)
    p.add_argument("--max-games",type=int,default=24)
    a=p.parse_args()
    if not 1<=a.days<=60 or not 1<=a.max_games<=30:
        raise ValueError("Backfill limits exceeded")
    url=os.environ.get("SUPABASE_URL","")
    key=os.environ.get("SUPABASE_SERVICE_ROLE_KEY","")
    if not url or not key:
        print("USAGE IMPORT BLOCKED: Supabase credentials missing")
        return 1
    today=dt.datetime.now(dt.timezone.utc).date()
    games=discover(today,a.days)
    counts=existing_counts(url,key,today-dt.timedelta(days=a.days))
    s=collect(games,counts,url=url,key=key,today=today,max_games=a.max_games)
    # No silent green when every attempted source call failed.
    return int(s["attempted"]>0 and s["rows_upserted"]==0)

if __name__=="__main__":
    raise SystemExit(main())
