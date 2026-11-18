#!/usr/bin/env python3
"""Recover 17 Nov 2026 bot-owned card identities from verified delivery logs.

Only exact, proven pairing:
  card run 44199830731: 18 singles + 6 ladders, IDs 2435..2458,
  matching 24 canonical database rows in original insertion order.
Never guess a Telegram message_id, never settle a result or invent a wager.
"""
import json,hashlib,os
from datetime import datetime,timezone
from pathlib import Path
import requests

DAY="2026-11-17"
RUN_ID=44199830731
IDS=list(range(2435,2459))
HISTORY=Path("picks_history.json")
ENDPOINT=os.environ.get("SUPABASE_URL","").rstrip("/")
KEY=os.environ.get("SUPABASE_KEY","")
CHAT=os.environ.get("TELEGRAM_CHAT_ID","")

def fetch():
    if not ENDPOINT or not KEY or not CHAT:
        raise RuntimeError("Supabase/Telegram secrets missing; no recovery")
    r=requests.get(ENDPOINT+"/rest/v1/prop_hunter_picks",
       headers={"apikey":KEY,**({"Authorization":"Bearer "+KEY} if not KEY.startswith(("sb_secret_","sb_publishable_")) else {})},
       params={"select":"*","date":"eq."+DAY,"order":"created_at.asc","limit":"100"},
       timeout=25)
    r.raise_for_status()
    rows=r.json()
    if not isinstance(rows,list) or len(rows)!=24:
        raise RuntimeError("recovery blocked: expected precisely 24 rows")
    if [int(x.get("id") or 0) for x in rows]!=list(range(1524,1548)):
        raise RuntimeError("recovery blocked: DB sequence differs from original 24 sends")
    if [x.get("pick_type") for x in rows] != ["single"]*18+["ladder"]*6:
        raise RuntimeError("recovery blocked: unexpected ticket order")
    for row in rows:
        ts=datetime.fromisoformat(str(row.get("created_at","")).replace("Z","+00:00"))
        if ts.tzinfo is None:raise RuntimeError("naive time")
        if not (datetime(2026,11,17,23,38,tzinfo=timezone.utc) <= ts <=
                datetime(2026,11,17,23,40,tzinfo=timezone.utc)):
            raise RuntimeError("recovery blocked: run time mismatch")
        if not row.get("dedup_key") or not row.get("player_name"):
            raise RuntimeError("recovery blocked: incomplete identity")
    return rows

def _combo_id(c):
    raw=json.dumps({"type":c.get("type"),"legs":c.get("legs"),"leg_details":c.get("leg_details"),
                    "odds":c.get("odds"),"stake":c.get("stake"),"created_at":c.get("created_at")},
                   sort_keys=True,default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

def recover():
    rows=fetch()
    history=json.loads(HISTORY.read_text(encoding="utf8"))
    if not isinstance(history,list):raise RuntimeError("history not list")
    existing=next((x for x in history if x.get("date")==DAY),None)
    if existing and existing.get("cards"):
        raise RuntimeError("day already has cards; refusing to remap originals")
    seen={int(c.get("message_id")) for e in history for c in (e.get("cards") or []) if c.get("message_id")}
    if any(m in seen for m in IDS):
        raise RuntimeError("message id already mapped in another date")
    entry=existing or {"date":DAY,"picks":[],"kombis":[],"cards":[]}
    if entry.get("picks") or entry.get("kombis"):
        raise RuntimeError("existing picks need manual reconciliation")
    for row,mid in zip(rows,IDS):
        raw=row.get("raw") if isinstance(row.get("raw"),dict) else {}
        typ=row["pick_type"]
        status=str(row.get("result") or row.get("status") or "pending")
        common={"date":DAY,"player":row["player_name"],"market":row["market"],
                "sport":row.get("sport") or row.get("league"),"direction":row.get("direction"),
                "point":row.get("line"),"line":row.get("line"),"odds":row.get("odds"),
                "stake":row.get("stake"),"probability":row.get("probability"),
                "dedup_key":row["dedup_key"],"game":raw.get("game"),
                "commence_time":raw.get("commence_time"),
                "features":row.get("features") or {},"result":status,
                "profit":row.get("profit"),"actual_value":row.get("actual_value")}
        if typ=="single":
            item=dict(common,type="single",team=row.get("team"),bookmaker=(row.get("features") or {}).get("bookmaker"),
                      created_at=row.get("created_at"))
            entry["picks"].append(item)
            scoped={"pick_keys":[row["dedup_key"]],"combo_ids":[]}
            visual=item
        else:
            item=dict(raw)
            item.update({k:v for k,v in common.items() if v is not None and k not in ("features",)})
            item["features"]=raw.get("features") or row.get("features") or {}
            item["type"]="ladder"
            item["created_at"]=raw.get("created_at") or row["created_at"]
            item["dedup_key"]=row["dedup_key"]
            item["combo_id"]=_combo_id(item)
            entry["kombis"].append(item)
            scoped={"pick_keys":[],"combo_ids":[item["combo_id"]]}
            visual=item
        # Internal label for future in-place settlement; PHOTO has no caption.
        label=f"{common['player']} · {common['market']} @{float(common['odds']):.2f}"
        text=f"🏀 PROP HUNTER · {typ.upper()}\n• {label}\n🏁 Auswertung: ⏳ offen\n@prophunter"
        entry["cards"].append({
            "created_at":row["created_at"],"message_id":int(mid),"chat_id":CHAT,
            "text":text,"card_kind":typ,"media_type":"photo","image_pick":visual,
            "recovered_from_run":RUN_ID,**scoped
        })
    if not existing:history.append(entry)
    history.sort(key=lambda x:str(x.get("date") or ""))
    HISTORY.write_text(json.dumps(history,ensure_ascii=False,indent=2,default=str),encoding="utf8")
    return {"date":DAY,"run_id":RUN_ID,"recovered":len(IDS),"singles":18,"ladders":6,
            "first_message_id":IDS[0],"last_message_id":IDS[-1]}

if __name__=="__main__":
    print("VERIFIED CARD IDENTITY RECOVERY "+json.dumps(recover()),flush=True)
