#!/usr/bin/env python3
"""
PROP HUNTER — LEARNING UPDATE
=============================

Lernt aus Settlements:
- ROI / Trefferquote pro Sport, Liga, Markt, Rule, Player
- schreibt prop_hunter_rule_performance
- schreibt prop_hunter_learning_summary.json
"""

from __future__ import annotations

from collections import defaultdict

from prop_hunter_shared_utils import (
    select_rows, upsert_rows, safe_json_write, log, norm_name, norm_market,
    to_float, hash_key, now_iso
)

OUT = "prop_hunter_learning_summary.json"

def profit_for_result(result: str, odds_decimal, stake=1.0) -> float:
    odds = to_float(odds_decimal, 1.0) or 1.0
    if result == "win":
        return stake * (odds - 1.0)
    if result == "loss":
        return -stake
    return 0.0

def key_parts(r):
    return {
        "sport": str(r.get("sport") or "UNKNOWN").upper(),
        "league": str(r.get("league") or "UNKNOWN").upper(),
        "market_key": norm_market(r.get("market") or "unknown"),
        "rule_id": str(r.get("rule_id") or r.get("pick_raw", {}).get("rule_id") or "unknown"),
        "player_key": norm_name(r.get("player_name") or "unknown"),
    }

def main():
    results = select_rows("prop_hunter_results", limit=20000)
    groups = defaultdict(lambda: {"bets": 0, "wins": 0, "losses": 0, "pushes": 0, "profit": 0.0, "stake": 0.0})
    for r in results:
        result = str(r.get("result") or "").lower()
        if result not in ("win", "loss", "push"):
            continue
        raw = r.get("pick_raw") or {}
        odds = raw.get("odds_decimal") or raw.get("odds") or raw.get("price")
        stake = to_float(raw.get("stake"), 1.0) or 1.0
        parts = key_parts(r)
        keys = [
            ("rule", parts["rule_id"]),
            ("market", parts["sport"] + "|" + parts["league"] + "|" + parts["market_key"]),
            ("player", parts["sport"] + "|" + parts["league"] + "|" + parts["player_key"]),
            ("sport_league", parts["sport"] + "|" + parts["league"]),
        ]
        for group_type, group_key in keys:
            g = groups[(group_type, group_key)]
            g["bets"] += 1
            g["stake"] += stake
            g["profit"] += profit_for_result(result, odds, stake)
            if result == "win":
                g["wins"] += 1
            elif result == "loss":
                g["losses"] += 1
            elif result == "push":
                g["pushes"] += 1

    rows = []
    for (group_type, group_key), g in groups.items():
        bets = g["bets"]
        wins = g["wins"]
        stake = g["stake"] or 1.0
        roi = g["profit"] / stake
        hit_rate = wins / bets if bets else 0
        weight = 1.0
        if bets >= 20:
            weight = max(0.70, min(1.30, 1.0 + roi * 0.25 + (hit_rate - 0.52) * 0.20))
        rows.append({
            "performance_id": hash_key(group_type, group_key),
            "group_type": group_type,
            "group_key": group_key,
            "bets": bets,
            "wins": g["wins"],
            "losses": g["losses"],
            "pushes": g["pushes"],
            "profit": round(g["profit"], 4),
            "stake": round(g["stake"], 4),
            "roi": round(roi, 6),
            "hit_rate": round(hit_rate, 6),
            "learning_weight": round(weight, 6),
            "updated_at": now_iso(),
        })

    safe_json_write(OUT, rows)
    upsert_rows("prop_hunter_rule_performance", rows, "performance_id")
    log(f"learning update done: groups={len(rows)}")

if __name__ == "__main__":
    main()
