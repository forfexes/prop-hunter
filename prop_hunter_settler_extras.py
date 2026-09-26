#!/usr/bin/env python3
"""Supplemental settlement for canonical markets not covered by the legacy map.

Covers MLB doubles/triples, canonical `threes`, and explicit rushing/receiving/
generic touchdown thresholds. Existing legacy-settled markets are intentionally
left to prop_hunter_settler.py to avoid duplicate grading paths.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from prop_hunter_settler import (
    find_gamelog, learn_aliases, line_of_pick, result_for_value, side_of_pick
)
from prop_hunter_shared_utils import (
    hash_key, log, norm_name, now_iso, pick_id, safe_json_write,
    select_pick_rows, select_rows, to_float, upsert_rows
)

OUT = "prop_hunter_results_extras_settled.json"

def detect_extra_stat(market: Any) -> Optional[str]:
    m = str(market or "").lower().replace("_", " ")
    if "triple" in m and "triple double" not in m:
        return "triples"
    if "double" in m and "double double" not in m:
        return "doubles"
    if "threes" in m or m.strip() == "3pt":
        return "threes_made"
    if "receiving touchdown" in m:
        return "receiving_touchdowns"
    if "rushing touchdown" in m:
        return "rushing_touchdowns"
    if "passing touchdown" in m:
        return None  # legacy settler already handles this correctly
    if "touchdown" in m or m.strip() in {"td", "tds"}:
        return "touchdowns"
    return None

def extra_stat_value(gl: Dict[str, Any], stat: str):
    direct = to_float(gl.get(stat))
    if direct is not None:
        return direct
    if stat == "touchdowns":
        rec = to_float(gl.get("receiving_touchdowns"), 0.0) or 0.0
        rush = to_float(gl.get("rushing_touchdowns"), 0.0) or 0.0
        return rec + rush
    raw = gl.get("raw") if isinstance(gl.get("raw"), dict) else {}
    split = raw.get("split") if isinstance(raw.get("split"), dict) else {}
    stats = split.get("stat") if isinstance(split.get("stat"), dict) else {}
    v = to_float(stats.get(stat))
    if v is not None:
        return v
    for value in raw.values():
        if isinstance(value, dict):
            split2 = value.get("split") if isinstance(value.get("split"), dict) else {}
            stats2 = split2.get("stat") if isinstance(split2.get("stat"), dict) else {}
            v = to_float(stats2.get(stat))
            if v is not None:
                return v
    return None

def _allowed(stat: str, league_or_sport: str) -> bool:
    s = league_or_sport.upper()
    if stat in {"doubles", "triples"}:
        return "MLB" in s or s == "BASEBALL"
    if stat == "threes_made":
        return any(x in s for x in ("NBA", "WNBA", "NCAAB", "BASKETBALL"))
    if stat in {"touchdowns", "receiving_touchdowns", "rushing_touchdowns"}:
        return any(x in s for x in ("NFL", "NCAAF", "AMERICAN_FOOTBALL", "FOOTBALL"))
    return False

def main() -> None:
    picks = select_pick_rows(limit=5000)
    logs = select_rows("prop_hunter_player_gamelogs", limit=20000)
    aliases = learn_aliases(list(picks) + list(logs))
    settled = []
    for p in picks:
        stat = detect_extra_stat(p.get("market") or p.get("prop_type") or p.get("selection"))
        if not stat:
            continue
        sport = str(p.get("league") or p.get("sport") or "").upper()
        if not _allowed(stat, sport):
            continue
        status_now = str(p.get("status") or p.get("result") or "pending").lower()
        if status_now not in {"", "pending", "open", "none", "null", "unsettled"}:
            continue
        gl = find_gamelog(p, logs, aliases=aliases)
        if not gl:
            continue
        value = extra_stat_value(gl, stat)
        line = line_of_pick(p)
        side = side_of_pick(p)
        status = result_for_value(value, line, side)
        if status == "no_result":
            continue
        pid = pick_id(p)
        settled.append({
            "result_id": hash_key(pid, stat, gl.get("game_id")),
            "pick_id": pid,
            "sport": p.get("sport") or gl.get("sport"),
            "league": p.get("league") or gl.get("league"),
            "player_name": p.get("player_name") or p.get("player") or gl.get("player_name"),
            "normalized_name": norm_name(p.get("player_name") or p.get("player") or gl.get("player_name")),
            "market": p.get("market") or p.get("prop_type") or p.get("selection"),
            "stat_key": stat,
            "line": line,
            "side": side,
            "actual_value": value,
            "result": status,
            "game_id": gl.get("game_id"),
            "settled_at": now_iso(),
            "pick_raw": p,
            "result_raw": gl,
        })
    safe_json_write(OUT, settled)
    upsert_rows("prop_hunter_results", settled, "result_id")
    log(f"extras settler done: picks={len(picks)} logs={len(logs)} settled={len(settled)}")

if __name__ == "__main__":
    main()
