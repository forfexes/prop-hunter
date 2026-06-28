import os
from prop_hunter_shared_utils import http_json, safe_json_write, upsert_rows, now_iso, log

OUT="prop_hunter_github_sources.json"
QUERIES=["topic:sports-analytics language:Python","topic:sports-data language:Python","topic:nba-stats language:Python",
"topic:nfl-stats language:Python","topic:mlb language:Python sports","topic:wnba","topic:sportsdataverse",
"topic:pybaseball","topic:nflverse","topic:statsbomb","topic:sofascore","topic:odds-api","topic:player-props",
"topic:football-data","topic:soccer-analytics","topic:fbref"]

def hdr():
    h={"Accept":"application/vnd.github+json"}
    t=os.getenv("GITHUB_TOKEN","").strip()
    if t: h["Authorization"]=f"Bearer {t}"
    return h

def risk(repo):
    stars=int(repo.get("stargazers_count") or 0); score=50
    if stars>=1000: score-=25
    elif stars>=100: score-=15
    if repo.get("archived"): score+=30
    if not repo.get("license"): score+=10
    return max(0,min(100,score))

def main():
    rows=[]
    for q in QUERIES[:int(os.getenv("GITHUB_QUERY_CAP","16"))]:
        data=http_json("https://api.github.com/search/repositories",params={"q":q,"sort":"updated","order":"desc","per_page":int(os.getenv("GITHUB_MAX_PER_QUERY","10"))},headers=hdr(),retries=1) or {}
        for r in data.get("items",[]):
            rows.append({"repo_id":str(r.get("id")),"full_name":r.get("full_name"),"url":r.get("html_url"),"description":r.get("description"),
            "language":r.get("language"),"stars":r.get("stargazers_count"),"forks":r.get("forks_count"),"open_issues":r.get("open_issues_count"),
            "license":(r.get("license") or {}).get("spdx_id"),"archived":r.get("archived"),"last_update":r.get("updated_at"),
            "query":q,"risk_score":risk(r),"source_type":"github_open_source","raw":r,"updated_at":now_iso()})
    out=list({r["repo_id"]:r for r in rows}.values())
    safe_json_write(OUT,out); upsert_rows("prop_hunter_github_sources",out,"repo_id")
    log(f"github scanner done {len(out)} repos")
if __name__=="__main__": main()
