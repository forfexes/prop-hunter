#!/usr/bin/env python3
"""Loescht doppelte Prop-Hunter-Karten in Telegram und raeumt picks_history.json auf.

Gleiche Karte = gleiche Signatur (Singles: pick_keys, Kombi/Ladder/Builder: Legs).
Die fruehste bleibt, spaetere werden geloescht. APPLY=1 fuehrt aus, sonst Dry-Run.
"""
import json, os, ast
from datetime import datetime, timezone, timedelta
import requests

HIST = "picks_history.json"
APPLY = os.getenv("APPLY", "0") == "1"
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
DAYS = int(os.getenv("DEDUP_DAYS", "2"))


def combo_sig(k):
    legs = k.get("leg_details") or k.get("ladder_legs") or []
    parts = []
    for l in legs:
        if isinstance(l, dict):
            parts.append((str(l.get("player") or l.get("team") or "").lower().strip(),
                          str(l.get("source_market") or l.get("market") or "").lower().strip(),
                          l.get("point"), str(l.get("direction") or "").lower()))
    return (str(k.get("type") or ""), frozenset(parts)) if parts else None


def lst(v):
    if isinstance(v, list):
        return v
    try:
        return list(ast.literal_eval(str(v)))
    except Exception:
        return []


def main():
    h = json.load(open(HIST))
    cutoff = (datetime.now(timezone.utc) - timedelta(days=DAYS)).strftime("%Y-%m-%d")
    to_delete = []
    for e in h:
        if e.get("date", "") < cutoff:
            continue
        by_id = {k.get("combo_id"): k for k in e.get("kombis", [])}
        seen = {}
        drop_cards, drop_combo_ids, drop_pick_keys = [], set(), set()
        for c in sorted(e.get("cards", []), key=lambda c: c.get("created_at") or ""):
            cids = lst(c.get("combo_ids"))
            if cids:
                sigs = frozenset(s for s in (combo_sig(by_id[i]) for i in cids if i in by_id) if s)
                sig = ("combo", sigs) if sigs else None
            else:
                pk = tuple(lst(c.get("pick_keys")))
                sig = ("single", pk) if pk else None
            if not sig:
                continue
            if sig in seen:
                drop_cards.append(c)
                drop_combo_ids.update(cids)
                drop_pick_keys.update(lst(c.get("pick_keys")))
            else:
                seen[sig] = c
        if not drop_cards:
            continue
        print(f"{e['date']}: {len(drop_cards)} doppelte Karten")
        for c in drop_cards:
            to_delete.append((c.get("chat_id"), c.get("message_id")))
        if APPLY:
            ids = {id(c) for c in drop_cards}
            e["cards"] = [c for c in e["cards"] if id(c) not in ids]
            e["kombis"] = [k for k in e.get("kombis", []) if k.get("combo_id") not in drop_combo_ids]
    print("zu loeschen:", len(to_delete))
    if not APPLY:
        return
    ok = fail = 0
    for chat, mid in to_delete:
        try:
            r = requests.post(f"https://api.telegram.org/bot{TOKEN}/deleteMessage",
                              json={"chat_id": chat, "message_id": int(mid)}, timeout=20)
            if r.ok and r.json().get("ok"):
                ok += 1
            else:
                fail += 1
                print("fail", mid, r.text[:120])
        except Exception as ex:
            fail += 1
            print("err", mid, ex)
    json.dump(h, open(HIST, "w"), ensure_ascii=False, indent=1)
    print(f"geloescht={ok} fehlgeschlagen={fail}")


if __name__ == "__main__":
    main()
