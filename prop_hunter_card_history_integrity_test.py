"""Offline regression: each delivered photo is linked to its own original tip and Telegram ID."""
import ast
import hashlib
import json
import os
import sys
import tempfile
import types
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace as N
from unittest.mock import patch

source=ast.parse(Path("prophunter_core_1391.py").read_text(encoding="utf-8"))
functions=[node for node in source.body if isinstance(node,ast.FunctionDef)
           and node.name in {"load_history","save_history","persist","persist_confirmed_telegram_cards"}]
assert len(functions)==4

class HistoricalPick:
    def __init__(self,**values): self.values=values
    def model_dump(self):return dict(self.values)

def key(player,market,point,direction):
    return "|".join(map(str,(player,market,point,direction))).lower()

module=types.ModuleType("prop_hunter_form_quality")
module.evidence=lambda features: features
db_rows=[]
scope={
    "os":os,"json":json,"hashlib":hashlib,"datetime":datetime,"timezone":timezone,
    "HistoricalPick":HistoricalPick,"dedup_key":key,
    "sb_insert":lambda row:db_rows.append(row),
    "TG_CHAT":"verified-test-chat",
    "log":N(info=lambda *args,**kw:None),
}
exec(compile(ast.Module(body=functions,type_ignores=[]),"<history integrity>","exec"),scope)

def pick(kind,player,market,odds):
    return N(type=kind,player=player,market=market,odds=odds,stake=1,
             direction="under",point=7.5,team="",source_sport="NBA",sport="NBA",
             emoji="🏀",probability=0.7,features={},legs=[],picks=[],
             leg_details=[{"player":player,"market":market,"odds":odds,
                           "point":7.5,"direction":"under"}] if kind=="ladder" else [],
             category=None)

picks=[pick("single","Player A","Rebounds Under 7.5",1.42),
       pick("ladder","Player B","Rebounds Ladder",1.52),
       pick("ladder","Player C","Points Ladder",1.86)]
def delivered(mid,kind,si=(),ci=(),player=""):
    return {"message_id":mid,"kind":kind,
            "single_indices":list(si),"combo_indices":list(ci),
            "text":f"Original {player} pending","media_type":"photo",
            "image_pick":{"type":kind,"player":player,"sport":"NBA",
                          "leg_details":[{"market":"Rebounds Under 7.5","odds":1.4}]}}
cards=[delivered(301,"single",si=(0,),player="Player A"),
       delivered(302,"ladder",ci=(0,),player="Player B"),
       delivered(303,"ladder",ci=(1,),player="Player C")]
with tempfile.TemporaryDirectory() as tmp:
    filename=Path(tmp)/"picks_history.json"
    scope["HISTORY_FILE"]=str(filename)
    with patch.dict(sys.modules,{"prop_hunter_form_quality":module}):
        scope["persist"](picks,telegram_message_id=301,
                         telegram_text="Original first",
                         telegram_cards=cards)
        history=scope["load_history"]()
        assert len(history)==1
        entry=history[0]
        assert len(entry["picks"])==1 and len(entry["kombis"])==2
        assert [c["message_id"] for c in entry["cards"]]==[301,302,303]
        assert len({c["message_id"] for c in entry["cards"]})==3
        assert [c["pick_keys"] for c in entry["cards"]]==[[key("Player A","Rebounds Under 7.5",7.5,"under")],[],[]]
        assert [len(c["combo_ids"]) for c in entry["cards"]]==[0,1,1]
        assert entry["cards"][1]["combo_ids"]!=entry["cards"][2]["combo_ids"]
        assert all(c["card_design_version"]==3 and c["media_type"]=="photo" for c in entry["cards"])
        assert all(c["image_pick"]["player"] in {"Player A","Player B","Player C"} for c in entry["cards"])
        original=filename.read_bytes()
        try:scope["persist"](picks,telegram_cards=cards)
        except RuntimeError:pass
        else:raise AssertionError("Duplicate IDs must reject the write")
        assert filename.read_bytes()==original
        try:scope["persist"](picks,telegram_cards=cards[:2])
        except RuntimeError:pass
        else:raise AssertionError("Incomplete delivery must reject the write")
        assert filename.read_bytes()==original
        filename.write_text("not valid JSON",encoding="utf-8")
        try:scope["load_history"]()
        except RuntimeError:pass
        else:raise AssertionError("Corrupted history must not silently reset to []")
        assert filename.read_text(encoding="utf-8")=="not valid JSON"
        filename.unlink()
        assert scope["persist_confirmed_telegram_cards"](picks,cards[:2])==2
        partial=scope["load_history"]()[0]
        assert [x["message_id"] for x in partial["cards"]]==[301,302]
        assert len(partial["picks"])==1 and len(partial["kombis"])==1
        assert partial["cards"][1]["combo_ids"]==[partial["kombis"][0]["combo_id"]]
print("TELEGRAM PER-CARD ID / LADDER MAPPING / ATOMIC HISTORY REGRESSIONS PASSED")
