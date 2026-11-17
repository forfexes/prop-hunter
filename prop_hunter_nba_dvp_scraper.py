#!/usr/bin/env python3
"""Public HTML NBA DvP collector. No credentials, access bypass or persistent DB.

Attempt 5 position-specific FantasyPros pages at most once per card run.
Reject stale/wrong-season, incomplete/ambiguous and HTML-block pages.
Only observed boxscore PTS/REB/AST/3PM, NEVER fantasy totals.
Do not publish/adjust probability directly from scraped data.
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from prop_hunter_nba_context_sources import observed_dvp

URL = "https://www.fantasypros.com/daily-fantasy/nba/fanduel-defense-vs-position.php"
POSITIONS = ("PG", "SG", "SF", "PF", "C")
STATS = {"PTS":"points","REB":"rebounds","AST":"assists","3PM":"threes"}
TEAM_CODES = frozenset(("ATL","BOS","BKN","CHA","CHI","CLE","DAL","DEN","DET","GSW","HOU","IND","LAC","LAL","MEM","MIA","MIL","MIN","NOP","NYK","OKC","ORL","PHI","PHX","POR","SAC","SAS","TOR","UTA","WAS"))


def current_season(day):
    start = day.year if day.month >= 10 else day.year - 1
    return f"{start}-{str(start+1)[-2:]}"


def parse_page(html, *, position, day):
    if position not in POSITIONS:
        raise ValueError("unknown position")
    soup=BeautifulSoup(html,"html.parser")
    page_text=soup.get_text(" ",strip=True)
    season=current_season(day)
    season_start=int(season[:4])
    heading=f"{season_start}-{season_start+1}"
    if not re.search(r"Defense\s+Vs\.?\s+Position",page_text,re.I) or heading not in page_text:
        raise ValueError("missing current-season DvP page header")
    evidence=[]
    for table in soup.find_all("table"):
        headers=[re.sub(r"\s+"," ",th.get_text(" ",strip=True)).upper() for th in table.select("thead th")]
        if not headers:
            # support traditional header rows where <th> live in <tr>.
            header=table.find("tr")
            headers=[th.get_text(" ",strip=True).upper() for th in header.find_all("th")] if header else []
        if not all(x in headers for x in ("TEAM","GP","PTS","REB","AST","3PM")):
            continue
        cells={name:headers.index(name) for name in ("TEAM","GP","PTS","REB","AST","3PM")}
        for tr in table.select("tbody tr"):
            tds=tr.find_all(["td","th"],recursive=False)
            if len(tds)<=max(cells.values()):
                continue
            label=tds[cells["TEAM"]].get_text(" ",strip=True).upper()
            match=re.match(r"^([A-Z]{2,3})(?:\s|$)",label)
            if not match:
                continue
            team=match.group(1)
            if team not in TEAM_CODES:continue
            try:
                gp=int(tds[cells["GP"]].get_text(" ",strip=True))
                if not 5<=gp<=85:continue
                for col,stat in STATS.items():
                    value=float(tds[cells[col]].get_text(" ",strip=True))
                    row={"source":"fantasypros_dvp","opponent_team":team,"position":position,"stat":stat,
                         "allowed_per_game":value,"games":gp,"season":season,"observed_on":day.isoformat()}
                    valid=observed_dvp(row,as_of=day.isoformat())
                    if valid:evidence.append(valid)
            except (ValueError,TypeError):
                continue
    grouped={}
    for row in evidence:
        key=(row["opponent_team"],row["position"],row["stat"])
        grouped.setdefault(key,[]).append(row)
    if any(len(items)!=1 for items in grouped.values()):
        raise ValueError("ambiguous multi-position/duplicate rows")
    teams={item["opponent_team"] for item in evidence}
    if len(teams)<25 or len(evidence)!=len(teams)*4:
        raise ValueError(f"incomplete DvP table: teams={len(teams)} values={len(evidence)}")
    return evidence


def collect(*, day=None, session=None, delay_seconds=0.3):
    day=day or datetime.now(timezone.utc).date()
    session=session or requests.Session()
    output=[]
    for position in POSITIONS:
        response=session.get(URL,params={"position":position,"year":day.year if day.month>=10 else day.year-1},
                             headers={"User-Agent":"Mozilla/5.0 (compatible; PropHunterResearch/1.0)"},
                             timeout=7)
        response.raise_for_status()
        output.extend(parse_page(response.text,position=position,day=day))
        if delay_seconds:time.sleep(delay_seconds)
    assert len(output)>=500, "insufficient position coverage"
    return {"collected_at":datetime.now(timezone.utc).isoformat(),
            "season":current_season(day),"source":"fantasypros_dvp",
            "rows":output,"model_ready":False}


def main():
    output=Path(os.getenv("PH_NBA_DVP_OUTPUT","output/nba_dvp_observed.json"))
    try:
        result=collect()
    except (requests.RequestException,ValueError,AssertionError) as exc:
        print(f"NBA DvP scraper UNAVAILABLE (no model data): {type(exc).__name__}: {str(exc)[:140]}",flush=True)
        return 0
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,separators=(",",":")),encoding="utf8")
    print(f"NBA DvP public source OK: rows={len(result['rows'])} season={result['season']} evidence-only",flush=True)
    return 0


if __name__=="__main__":
    sys.exit(main())
