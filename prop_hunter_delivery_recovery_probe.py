#!/usr/bin/env python3
"""Read-only recovery audit for GitHub Actions card sends and missing history.

Uses GH_TOKEN solely to query workflows. Exports no token, text card bodies,
player data or raw job logs. Does not mutate Telegram or history.
"""
import json,os,re,sys,urllib.request,urllib.error
from datetime import datetime,timezone
from pathlib import Path

REPO=os.environ.get("GITHUB_REPOSITORY","forfexes/prop-hunter")
TOKEN=os.environ.get("GH_TOKEN","")
BASE=f"https://api.github.com/repos/{REPO}"
HEADERS={"Accept":"application/vnd.github+json","User-Agent":"PropHunter-Delivery-Recovery/1.0"}
if TOKEN:HEADERS["Authorization"]="Bearer "+TOKEN

def get(path,maxbytes=8000000):
    req=urllib.request.Request(BASE+path,headers=HEADERS)
    with urllib.request.urlopen(req,timeout=18) as r:
        result=r.read(maxbytes)
    return result

def parse_delivery(log):
    """Extract only confirmed message IDs and delivery count."""
    out=[]
    for line in log.splitlines():
        if "Telegram OK message_id=" not in line or "ids=" not in line:continue
        found=re.search(r"Telegram OK message_id=(\d+) messages=(\d+) ids=\[([^]]+)\]",line)
        if not found:continue
        mids=[int(x) for x in re.findall(r"\d+",found.group(3))]
        if len(mids)==int(found.group(2)) and len(set(mids))==len(mids) and mids[0]==int(found.group(1)):
            out.append({"first_message_id":mids[0],"message_ids":mids,"count":len(mids)})
    return out

def run_audit():
    out={"checked_at":datetime.now(timezone.utc).isoformat(),"runs":[],"errors":[]}
    try:
        data=json.loads(get("/actions/workflows/prophunter.yml/runs?per_page=18"))
        runs=data.get("workflow_runs",[])
    except Exception as exc:
        out["errors"].append("workflow_run_lookup: "+type(exc).__name__+" "+str(exc)[:110])
        return out
    for run in runs:
        info={"run_id":run.get("id"),"conclusion":run.get("conclusion"),
              "created_at":run.get("created_at"),"head_sha":str(run.get("head_sha") or "")[:12],
              "jobs":[],"deliveries":[]}
        try:
            jobs=json.loads(get(f"/actions/runs/{run['id']}/jobs?per_page=50")).get("jobs",[])
        except Exception as exc:
            info["error"]="jobs:"+type(exc).__name__
            out["runs"].append(info)
            continue
        for job in jobs:
            j={"name":job.get("name"),"conclusion":job.get("conclusion"),
               "failed_steps":[x.get("name") for x in job.get("steps",[]) if x.get("conclusion")=="failure"]}
            info["jobs"].append(j)
            if j["name"] != "card" and "card" not in str(j["name"] or "").lower():
                continue
            try:
                body=get(f"/actions/jobs/{job['id']}/logs").decode("utf-8","replace")
                info["deliveries"].extend(parse_delivery(body))
                if "Telegram OK message_id=" in body and not info["deliveries"]:
                    j["parse_warning"]="Telegram OK log not parseable"
                if "Save card state" in body:
                    j["save_history_step_present"]=True
            except Exception as exc:
                j["logs_error"]=type(exc).__name__+" "+str(exc)[:70]
        out["runs"].append(info)
    return out

if __name__=="__main__":
    d=run_audit()
    p=Path("diagnostics/prop_hunter_delivery_recovery_probe.json")
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(d,indent=2),encoding="utf-8")
    print("DELIVERY_RECOVERY_AUDIT "+json.dumps({"runs":len(d["runs"]),"errors":d["errors"],
          "delivered_runs":sum(bool(x.get("deliveries")) for x in d["runs"])}),flush=True)
