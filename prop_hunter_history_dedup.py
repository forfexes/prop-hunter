#!/usr/bin/env python3
"""Entfernt Doppelzaehlungen aus picks_history.json (nur Statistik, kein Telegram).

- Singles mit gleichem dedup_key am selben Tag: der fruehste bleibt, Rest wird entfernt.
- Kombi/Ladder/Builder mit gleichen Legs: der fruehste bleibt; Duplikat mit Telegram-Karte
  wird auf void gesetzt (Karte bleibt auswertbar, zaehlt aber nicht), ohne Karte entfernt.
APPLY=1 schreibt, sonst Dry-Run.
"""
import json, os
APPLY = os.getenv("APPLY", "0") == "1"
H = "picks_history.json"


def sig(k):
    legs = k.get("leg_details") or k.get("ladder_legs") or []
    parts = frozenset((str(l.get("player") or l.get("team") or "").lower(),
                       str(l.get("source_market") or l.get("market") or ""),
                       l.get("point"), l.get("direction"))
                      for l in legs if isinstance(l, dict))
    return (k.get("type"), parts) if parts else None


def main():
    h = json.load(open(H))
    rm_s = rm_k = void_k = 0
    for e in h:
        seen = set(); keep = []
        for p in sorted(e.get("picks", []), key=lambda p: p.get("created_at") or ""):
            k = p.get("dedup_key") or (p.get("player"), p.get("market"), p.get("point"), p.get("direction"))
            if k in seen:
                rm_s += 1
                continue
            seen.add(k); keep.append(p)
        if APPLY:
            order = {id(p): i for i, p in enumerate(e.get("picks", []))}
            e["picks"] = sorted(keep, key=lambda p: order[id(p)])
        carded = {i for c in e.get("cards", []) for i in (c.get("combo_ids") if isinstance(c.get("combo_ids"), list) else [])}
        seen = set(); out = []
        for k in sorted(e.get("kombis", []), key=lambda k: k.get("created_at") or ""):
            s = sig(k)
            if s and s in seen:
                if k.get("combo_id") in carded:
                    void_k += 1
                    if APPLY and k.get("result") in (None, "", "pending", "open"):
                        k["result"] = "void"; k["profit"] = 0
                        k.setdefault("features", {})["duplicate"] = True
                    out.append(k)
                else:
                    rm_k += 1
                continue
            if s:
                seen.add(s)
            out.append(k)
        if APPLY:
            e["kombis"] = out
    print(f"singles entfernt={rm_s} kombis entfernt={rm_k} kombis void(Karte vorhanden)={void_k}")
    if APPLY:
        json.dump(h, open(H, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
