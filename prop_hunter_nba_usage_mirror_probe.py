"""Read-only verification of independently hosted NBA advanced game logs.

Upstream: https://github.com/llimllib/nba_data (NBA PlayerGameLogs Advanced).
Source has its own provenance; never relabel it as BoxScoreUsageV3.
No database writes, credentials, or Telegram. Report only counts/freshness.
"""
import collections
import datetime as dt
import json
import math
import re
import tempfile
from urllib.request import Request, urlopen

BASE = "https://basketball-data.billmill.org/nba/stats/player_game_logs"
LIMIT = 24 * 1024 * 1024

def validate(rows, today, days=45):
    earliest=today-dt.timedelta(days=days)
    games=collections.defaultdict(list)
    seen=set()
    for row in rows:
        gid=str(row.get("game_id") or "")
        if not re.fullmatch(r"002[0-9]{7}",gid):
            continue
        try:
            day=dt.date.fromisoformat(str(row["game_date"])[:10])
            pid=str(row["player_id"])
            team=str(row["team_id"])
            minutes=float(row["min"])
            rate=float(row["usg_pct"])
        except (ValueError, TypeError, KeyError):
            continue
        if (not earliest<=day<=today or not pid.isdigit() or int(pid)<=0
                or not team.isdigit() or int(team)<=0 or not math.isfinite(minutes)
                or minutes<=0 or not math.isfinite(rate) or not 0<=rate<=1
                or not isinstance(row.get("win"),bool)):
            continue
        key=(gid,pid)
        if key in seen:
            raise ValueError("Duplicate canonical game/player identity")
        seen.add(key)
        games[gid].append((day,pid,team,row["win"],rate))
    accepted=[]
    for gid,items in games.items():
        if len({x[0] for x in items})!=1:
            raise ValueError("Conflicting game dates")
        outcomes={}
        for day,pid,team,win,rate in items:
            if team in outcomes and outcomes[team]!=win:
                raise ValueError("Conflicting team outcome")
            outcomes[team]=win
        if sorted(outcomes.values()) != [False,True]:
            continue
        accepted.extend((gid,*x) for x in items)
    counts=collections.Counter(x[2] for x in accepted)
    return {"source":"billmill_nba_playergamelogs_advanced",
            "games":len({x[0] for x in accepted}),"players":len(counts),
            "observations":len(accepted),
            "newest":max((str(x[1]) for x in accepted),default=None),
            "players_l5":sum(n>=5 for n in counts.values()),
            "players_l10":sum(n>=10 for n in counts.values()),
            "players_l15":sum(n>=15 for n in counts.values())}

def main():
    import pyarrow.parquet as pq
    today=dt.datetime.now(dt.timezone.utc).date()
    season=today.year+int(today.month>=10)
    url=f"{BASE}/season={season}/data.parquet"
    with tempfile.TemporaryFile() as fp:
        with urlopen(Request(url,headers={"User-Agent":"PropHunterDataValidation/1.0"}),timeout=30) as response:
            size=0
            while True:
                data=response.read(65536)
                if not data: break
                size+=len(data)
                if size>LIMIT: raise ValueError("Mirror file exceeds download budget")
                fp.write(data)
        fp.seek(0)
        pf=pq.ParquetFile(fp)
        cols=["game_id","game_date","player_id","team_id","min","usg_pct","win"]
        if not set(cols)<=set(pf.schema_arrow.names):
            raise ValueError("Required documented mirror columns missing")
        if pf.metadata.num_rows>200000: raise ValueError("Unexpected mirror row count")
        report=validate(pf.read(columns=cols).to_pylist(),today)
    print(json.dumps(report,sort_keys=True))
    if not report["observations"]:
        raise SystemExit("No valid game usage observations")
    if dt.date.fromisoformat(report["newest"]) < today-dt.timedelta(days=4):
        raise SystemExit("Mirror stale; do not use for current NBA form")

if __name__=="__main__":
    main()
