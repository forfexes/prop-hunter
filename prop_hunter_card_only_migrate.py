#!/usr/bin/env python3
"""One-shot visual-only migration of existing Telegram PROP HUNTER cards.

Does not settle tickets, fetch results, create bets or modify odds. Only bot-owned
historical cards whose original message_id is stored can be updated. Photo edits
keep the original message id; recent text->photo uses a guarded replacement.
"""
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

from prophunter_results import (
    _load_history, _save_history, _decorate_card, _card_pick, _edit_message,
    _replace_recent_text_with_photo,
)

MAX_UPDATES=max(1,min(60,int(os.getenv("PH_CARD_ONLY_MAX_UPDATES","30"))))
LOOKBACK_DAYS=max(1,min(30,int(os.getenv("PH_CARD_ONLY_LOOKBACK_DAYS","7"))))
VERSION=3


def migrate():
    history=_load_history()
    now=datetime.now(timezone.utc)
    cutoff=(now-timedelta(days=LOOKBACK_DAYS)).date().isoformat()
    counts={"candidates":0,"photo_updated":0,"text_replaced":0,
            "skipped":0,"failed":0}
    for entry in sorted(history,key=lambda x:str(x.get("date") or ""),reverse=True):
        if str(entry.get("date") or "")[:10] < cutoff:
            continue
        picks=entry.get("picks") or []
        combos=entry.get("kombis") or []
        for card in reversed(entry.get("cards") or []):
            if counts["photo_updated"]+counts["text_replaced"] >= MAX_UPDATES:
                return counts
            if card.get("tg_gone") or not card.get("message_id") or int(card.get("card_design_version") or 0)>=VERSION:
                counts["skipped"]+=1
                continue
            text=_decorate_card(card,picks,combos)
            visual=card.get("image_pick") or _card_pick(card,picks,combos)
            if not text or not visual:
                counts["skipped"]+=1
                continue
            counts["candidates"]+=1
            visual=dict(visual)
            latest=_card_pick(card,picks,combos)
            if latest:
                for k in ("result","actual_value","profit","leg_details","ladder_legs"):
                    if k in latest:
                        visual[k]=latest[k]
                for k in ("commence_time","game_date","date"):
                    if not visual.get(k) and latest.get(k):
                        visual[k]=latest[k]
            if card.get("media_type")=="photo":
                ok=_edit_message(card["message_id"],text,card.get("chat_id"),image_pick=visual)
                if ok:
                    card["card_design_version"]=VERSION
                    card["image_pick"]=visual
                    card["settlement_text"]=text
                    card["settlement_updated_at"]=now.isoformat()
                    counts["photo_updated"]+=1
                    _save_history(history)
                else:
                    counts["failed"]+=1
            elif card.get("media_type","text")=="text":
                ok=_replace_recent_text_with_photo(card,visual,text)
                if ok:
                    counts["text_replaced"]+=1
                    _save_history(history)
                else:
                    counts["skipped"]+=1
            else:
                counts["skipped"]+=1
    return counts


if __name__=="__main__":
    result=migrate()
    status={"checked_at":datetime.now(timezone.utc).isoformat(),**result}
    report=Path("diagnostics/prop_hunter_card_only_migration_status.json")
    report.parent.mkdir(parents=True,exist_ok=True)
    report.write_text(json.dumps(status,indent=2),encoding="utf-8")
    print("PROP HUNTER v3 CARD MIGRATION: "+json.dumps(status,sort_keys=True),flush=True)
