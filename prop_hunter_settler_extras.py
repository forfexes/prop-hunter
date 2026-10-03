#!/usr/bin/env python3
"""Supplemental exact settlement for markets that need threshold repair.

Runs after the unified legacy settler and deliberately reuses the legacy result id
when both paths see the same pick. That means an exact double/triple/TD grading
REPLACES a coarse legacy grading instead of creating a second learning sample.

Also covers NFL/NCAAF prop families exposed by the keyless adapters that the
legacy settler did not originally map (carries/rushing attempts and targets).
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

from prop_hunter_settler import (
    build_log_index, detect_stat as legacy_detect_stat, find_gamelog, learn_aliases, line_of_pick,
    result_for_value, side_of_pick
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
    if any(x in m for x in ("rushing attempts", "rush attempts", "carries")):
        return "rushing_attempts"
    if any(x in m for x in ("receiving targets", "receiver targets")) or m.strip() == "targets":
        return "receiving_targets"
    if "passing completions" in m or "pass completions" in m:
        return "passing_completions"
    if "passing attempts" in m or "pass attempts" in m:
        return "passing_attempts"
    if "receiving touchdown" in m:
        return "receiving_touchdowns"
    if "rushing touchdown" in m:
        return "rushing_touchdowns"
    if "passing touchdown" in m:
        return None
    if "touchdown" in m or m.strip() in {"td", "tds"}:
        return "touchdowns"
    return None

def extra_stat_value(gl: Dict[str, Any], stat: str):
    direct = to_float(gl.get(stat))
    if direct is not None:
        return direct
    aliases = {
        "receiving_targets": ("targets", "receiving_targets"),
        "rushing_attempts": ("carries", "rushing_attempts"),
        "passing_completions": ("completions", "passing_completions"),
        "passing_attempts": ("attempts", "passing_attempts"),
    }
    for key in aliases.get(stat, ()):
        value = to_float(gl.get(key))
        if value is not None:
            return value
    if stat == "touchdowns":
        rec = to_float(gl.get("receiving_touchdowns"), 0.0) or 0.0
        rush = to_float(gl.get("rushing_touchdowns"), 0.0) or 0.0
        return rec + rush
    raw = gl.get("raw") if isinstance(gl.get("raw"), dict) else {}
    v = to_float(raw.get(stat))
    if v is not None:
        return v
    for key in aliases.get(stat, ()):
        v = to_float(raw.get(key))
        if v is not None:
            return v
    if stat in {"passing_completions", "passing_attempts"}:
        cats = raw.get("categories") if isinstance(raw.get("categories"), dict) else {}
        for cat, values in cats.items():
            if "pass" not in str(cat).lower() or not isinstance(values, dict):
                continue
            catt = str(values.get("c_att") or values.get("c_att_") or "")
            m = re.fullmatch(r"\s*(\d+)\s*[/\-]\s*(\d+)\s*", catt)
            if m:
                return float(m.group(1 if stat == "passing_completions" else 2))
    split = raw.get("split") if isinstance(raw.get("split"), dict) else {}
    stats = split.get("stat") if isinstance(split.get("stat"), dict) else {}
    v = to_float(stats.get(stat))
    if v is not None:
        return v
    for key in aliases.get(stat, ()):
        v = to_float(stats.get(key))
        if v is not None:
            return v
    for value in raw.values():
        if isinstance(value, dict):
            split2 = value.get("split") if isinstance(value.get("split"), dict) else {}
            stats2 = split2.get("stat") if isinstance(split2.get("stat"), dict) else {}
            v = to_float(stats2.get(stat))
            if v is not None:
                return v
            for key in aliases.get(stat, ()):
                v = to_float(stats2.get(key))
                if v is not None:
                    return v
            v = to_float(value.get(stat))
            if v is not None:
                return v
            for key in aliases.get(stat, ()):
                v = to_float(value.get(key))
                if v is not None:
                    return v
    return None

def extra_line_of_pick(pick: Dict[str, Any], stat: str) -> Optional[float]:
    line = line_of_pick(pick)
    text = str(pick.get("market") or pick.get("prop_type") or pick.get("selection") or "")
    m = re.search(r"\b(\d+)\s*\+", text)
    if m:
        visible = float(int(m.group(1)))
        threshold = max(0.5, visible - 0.5)
        if line is None or abs(float(line) - visible) < 1e-9:
            line = threshold
    if line is None and stat in {"doubles", "triples"}:
        line = 0.5
    return line

def _allowed(stat: str, league_or_sport: str) -> bool:
    s = league_or_sport.upper()
    if stat in {"doubles", "triples"}:
        return "MLB" in s or s == "BASEBALL"
    if stat == "threes_made":
        return any(x in s for x in ("NBA", "WNBA", "NCAAB", "BASKETBALL"))
    if stat in {
        "touchdowns", "receiving_touchdowns", "rushing_touchdowns",
        "rushing_attempts", "receiving_targets", "passing_completions", "passing_attempts",
    }:
        return any(x in s for x in ("NFL", "NCAAF", "AMERICAN_FOOTBALL", "FOOTBALL"))
    return False

def main() -> None:
    picks = select_pick_rows(limit=5000)
    pending_status = {"", "pending", "open", "none", "null", "unsettled"}
    picks = [
        p for p in picks
        if str(p.get("status") or p.get("result") or "pending").lower() in pending_status
    ]
    logs = select_rows(
        "prop_hunter_player_gamelogs",
        limit=8000,
        order_by="id",
        desc=True,
    )
    aliases = learn_aliases(list(picks) + list(logs))
    log_index = build_log_index(logs)
    settled = []
    for p in picks:
        market = p.get("market") or p.get("prop_type") or p.get("selection")
        stat = detect_extra_stat(market)
        if not stat:
            continue
        sport = str(p.get("league") or p.get("sport") or "").upper()
        if not _allowed(stat, sport):
            continue
        status_now = str(p.get("status") or p.get("result") or "pending").lower()
        if status_now not in {"", "pending", "open", "none", "null", "unsettled"}:
            continue
        gl = find_gamelog(p, logs, aliases=aliases, log_index=log_index)
        if not gl:
            continue
        value = extra_stat_value(gl, stat)
        line = extra_line_of_pick(p, stat)
        side = side_of_pick(p)
        status = result_for_value(value, line, side)
        if status == "no_result":
            continue
        pid = pick_id(p)
        result_key_stat = legacy_detect_stat(market) or stat
        settled.append({
            "result_id": hash_key(pid, result_key_stat, gl.get("game_id")),
            "pick_id": pid,
            "sport": p.get("sport") or gl.get("sport"),
            "league": p.get("league") or gl.get("league"),
            "player_name": p.get("player_name") or p.get("player") or gl.get("player_name"),
            "normalized_name": norm_name(p.get("player_name") or p.get("player") or gl.get("player_name")),
            "market": market,
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
