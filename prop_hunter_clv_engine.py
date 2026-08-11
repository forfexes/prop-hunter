#!/usr/bin/env python3
"""PROP HUNTER — canonical CLV engine.

Reads current prop_hunter_picks (and legacy prop_picks as a read-only fallback),
matches same-book snapshots, computes line/odds CLV, writes the canonical
Supabase schema, and emits a JSON report.
"""
from __future__ import annotations

from datetime import datetime
from prop_hunter_shared_utils import (
    select_rows, upsert_rows, safe_json_write, log, norm_name,
    norm_market, to_float, to_int, hash_key, now_iso, pick_id,
)

OUT = "prop_hunter_clv_report.json"


def _text(v):
    return str(v or "").strip().lower()


def same(p, s):
    pn = norm_name(p.get("player") or p.get("player_name") or p.get("selection"))
    sn = norm_name(s.get("player") or s.get("player_name"))
    if pn and sn and pn != sn:
        return False
    pm = norm_market(p.get("market") or p.get("prop_type") or p.get("selection"))
    sm = norm_market(s.get("market") or s.get("market_key"))
    if pm and sm and not (pm in sm or sm in pm):
        return False
    gid = str(p.get("event_id") or p.get("game_id") or p.get("source_game_id") or "")
    sg = str(s.get("event_id") or s.get("game_id") or s.get("source_event_id") or "")
    return not (gid and sg and gid != sg)


def same_book(p, s):
    pb = _text(p.get("book") or p.get("bookmaker"))
    sb = _text(s.get("book") or s.get("bookmaker"))
    return not (pb and sb and pb != sb)


def side(p):
    t = _text(p.get("side") or p.get("direction") or p.get("selection") or p.get("market"))
    return "under" if "under" in t else "over"


def line_clv(pick_line, close_line, sd):
    pl, cl = to_float(pick_line), to_float(close_line)
    if pl is None or cl is None:
        return None
    return pl - cl if sd == "under" else cl - pl


def odds_clv(pick_odds, close_odds):
    po, co = to_float(pick_odds), to_float(close_odds)
    if not po or not co or po <= 1 or co <= 1:
        return None
    # Positive = pick price was better than closing price.
    return round((1.0 / co - 1.0 / po) * 100.0, 4)


def _created_at(row):
    return str(row.get("created_at") or "")


def _pick_created(p):
    return str(p.get("created_at") or "")


def _choose_snapshots(p, candidates):
    candidates = [s for s in candidates if same_book(p, s)]
    if not candidates:
        return None, None
    candidates.sort(key=_created_at)
    pick_ts = _pick_created(p)
    if pick_ts:
        before = [s for s in candidates if _created_at(s) <= pick_ts]
        opening = before[-1] if before else candidates[0]
    else:
        opening = candidates[0]
    closing = candidates[-1]
    return opening, closing


def _clv_row(p, opening, closing):
    sd = side(p)
    po = p.get("odds") or p.get("odds_decimal") or p.get("price") or opening.get("odds")
    pl = p.get("line") or p.get("prop_line") or p.get("points") or opening.get("line")
    pid = to_int(p.get("id"))
    clv_key = hash_key(pick_id(p), closing.get("id") or closing.get("snapshot_id"), closing.get("created_at"))
    return {
        "pick_id": pid,
        "sent_odds": to_float(po),
        "closing_odds": to_float(closing.get("odds") or closing.get("odds_decimal")),
        "sent_line": to_float(pl),
        "closing_line": to_float(closing.get("line")),
        "clv_odds_pct": odds_clv(po, closing.get("odds") or closing.get("odds_decimal")),
        "clv_line_diff": line_clv(pl, closing.get("line"), sd),
        "book": closing.get("book") or closing.get("bookmaker"),
        "source": closing.get("source"),
        "raw": {
            "clv_key": clv_key,
            "pick": p,
            "opening": opening,
            "closing": closing,
            "side": sd,
            "computed_at": now_iso(),
        },
    }


def main():
    current = select_rows("prop_hunter_picks", limit=5000)
    legacy = select_rows("prop_picks", limit=5000)
    picks = current + [p for p in legacy if pick_id(p) not in {pick_id(x) for x in current}]
    snaps = select_rows("prop_hunter_prop_snapshots", limit=50000)

    rows = []
    report = []
    existing = select_rows("prop_hunter_clv", limit=50000)
    existing_keys = {
        str((r.get("raw") or {}).get("clv_key"))
        for r in existing
        if isinstance(r.get("raw"), dict) and (r.get("raw") or {}).get("clv_key")
    }

    for p in picks:
        candidates = [s for s in snaps if same(p, s)]
        opening, closing = _choose_snapshots(p, candidates)
        if not opening or not closing:
            continue
        row = _clv_row(p, opening, closing)
        key = row["raw"]["clv_key"]
        if key not in existing_keys and row["pick_id"] is not None:
            rows.append(row)
        report.append({**row, "pick_id": pick_id(p), "player": p.get("player") or p.get("player_name"), "market": p.get("market")})

    safe_json_write(OUT, report)
    if rows:
        upsert_rows("prop_hunter_clv", rows, None)
    log(f"clv done report={len(report)} db_new={len(rows)}")


if __name__ == "__main__":
    main()
