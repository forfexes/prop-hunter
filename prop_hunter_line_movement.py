#!/usr/bin/env python3
"""Build a compact line-movement/steam report from stored prop snapshots.

No new Supabase table is required. The report is written locally and one health
summary is appended to prop_hunter_source_audit when Supabase is available.
"""
from __future__ import annotations

from collections import Counter

from prop_hunter_market_intelligence import movement_index
from prop_hunter_shared_utils import select_rows, safe_json_write, upsert_rows, now_iso, log

OUT = "prop_hunter_line_movement_report.json"


def main() -> None:
    rows = select_rows("prop_hunter_prop_snapshots", limit=50000)
    idx = movement_index(rows)
    report = []
    for key, info in idx.items():
        book, event, player, market, direction = key
        report.append({
            "bookmaker": book,
            "event": event,
            "player": player,
            "market": market,
            "direction": direction,
            **info,
        })
    report.sort(key=lambda r: (bool(r.get("steam")), float(r.get("movement_strength") or 0)), reverse=True)
    safe_json_write(OUT, report)
    steam = [r for r in report if r.get("steam")]
    books = Counter(r.get("bookmaker") for r in report if r.get("bookmaker"))
    audit = [{
        "source_name": "market_intelligence",
        "sport": "ALL",
        "check_type": "line_movement",
        "status": "active" if report else "empty",
        "message": f"markets={len(report)} steam={len(steam)}",
        "latency_ms": 0,
        "raw": {
            "markets": len(report),
            "steam": len(steam),
            "books": dict(books.most_common(20)),
            "generated_at": now_iso(),
        },
    }]
    try:
        upsert_rows("prop_hunter_source_audit", audit, None)
    except Exception:
        pass
    log(f"line movement done: markets={len(report)} steam={len(steam)}")


if __name__ == "__main__":
    main()
