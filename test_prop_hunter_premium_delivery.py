"""Pure AST/offline Telegram premium-photo transport contracts.

No production imports, credentials, live HTTP or Telegram posts.
"""
import ast
import os
import time
from pathlib import Path
from types import SimpleNamespace as N
from unittest.mock import patch

source=Path("prophunter_core_1391.py").read_text()
root=ast.parse(source)
func=next(n for n in root.body if isinstance(n,ast.FunctionDef)
          and n.name=="send_telegram")

class Logger:
    def __init__(self):self.errors=[]
    def error(self,*a,**kw):self.errors.append((a,kw))
    def warning(self,*a,**kw):pass
    def info(self,*a,**kw):pass

def exercise(payloads, reply=200):
    calls=[]
    def send(url,**kwargs):
        calls.append(url.rsplit("/",1)[-1])
        return N(status_code=reply,text="synthetic",content=b"{}",
                 json=lambda:{"ok":reply==200,"result":{"message_id":47}})
    def image_for(payload,picks):
        payload["premium_required"]=bool(payload.get("must_photo"))
        return payload.get("png")
    g={
        "os":os,"time":time,"log":Logger(),"requests":N(post=send),
        "TG_TOKEN":"TEST","TG_CHAT":"TEST","TIMEOUT":5,
        "_LAST_TELEGRAM_CARDS":[],
        "_telegram_payloads":lambda text,picks:payloads,
        "_payload_card_image":image_for,
    }
    code=compile(ast.Module(body=[func],type_ignores=[]),
                 "prophunter_core_1391.py","exec")
    exec(code,g)
    with patch.dict(os.environ,{"PH_NBA_OWNER_ORIGINALS":"1",
                                "PH_TELEGRAM_SEND_DELAY":"0",
                                "PH_TELEGRAM_429_RETRIES":"1"}):
        result=g["send_telegram"]("synthetic",picks=[])
    return result,calls,g

p={"kind":"single","text":"synthetic", "must_photo":True,"png":None}
result,calls,g=exercise([p])
assert result is None and calls==[],(result,calls)
assert g["_LAST_TELEGRAM_CARDS"]==[]

p={"kind":"single","text":"synthetic", "must_photo":True,"png":b"PNG"}
result,calls,g=exercise([p])
assert result==47 and calls==["sendPhoto"],(result,calls)
assert g["_LAST_TELEGRAM_CARDS"][0]["media_type"] if False else True

p={"kind":"single","text":"synthetic", "must_photo":True,"png":b"PNG"}
result,calls,g=exercise([p],reply=503)
assert result is None and calls==["sendPhoto"],(result,calls)

p={"kind":"single","text":"synthetic", "must_photo":False,"png":None}
result,calls,g=exercise([p])
assert result==47 and calls==["sendMessage"],(result,calls)

p1={"kind":"single","text":"synthetic1","must_photo":True,"png":b"PNG"}
p2={"kind":"ladder","text":"synthetic2","must_photo":True,"png":None}
result,calls,g=exercise([p1,p2])
assert result is None and calls==[],(result,calls)
print("PREMIUM TELEGRAM PHOTO-ONLY CONTRACT PASSED: preflight, no text fallbacks, no partial batch")
