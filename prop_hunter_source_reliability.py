#!/usr/bin/env python3
"""Learns source/bookmaker reliability from freshness, matching, CLV and results."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List

from prop_hunter_shared_utils import now_iso, safe_json_load, safe_json_write, select_rows, to_float, upsert_rows


def _source(row: Dict[str, Any]) -> str:
    raw = row.get("pick_raw") if isinstance(row.get("pick_raw"), dict) else {}
    return str(row.get("source") or row.get("bookmaker") or raw.get("source") or raw.get("bookmaker") or "unknown").lower()


def learn() -> List[Dict[str, Any]]:
    snapshots = select_rows("prop_hunter_prop_snapshots", limit=10000)
    results = select_rows("prop_hunter_results", limit=10000)
    health = safe_json_load("prop_hunter_source_health.json", []) or []
    stats: Dict[str, Dict[str, float]] = defaultdict(lambda: {
        "snapshots": 0, "odds": 0, "matched": 0, "settled": 0, "wins": 0, "profit": 0, "clv_sum": 0, "clv_n": 0,
        "health_active": 0, "health_total": 0,
    })
    for row in snapshots:
        src = _source(row); s = stats[src]; s["snapshots"] += 1
        if to_float(row.get("odds_decimal")): s["odds"] += 1
        if row.get("player_name") and row.get("market_key") and row.get("line") is not None: s["matched"] += 1
    for row in results:
        src = _source(row); s = stats[src]
        result = str(row.get("result") or "").lower()
        if result in {"win", "loss", "won", "lost", "hit", "miss"}:
            s["settled"] += 1; s["wins"] += int(result in {"win", "won", "hit"})
            s["profit"] += to_float(row.get("profit"), 0.0) or 0.0
        clv = to_float(row.get("clv_pct"))
        if clv is not None: s["clv_sum"] += clv; s["clv_n"] += 1
    for item in health:
        src = str(item.get("item_key") or "").replace("browser_", "").split("_")[0]
        if not src: continue
        stats[src]["health_total"] += 1
        if item.get("status") in {"active", "cached"}: stats[src]["health_active"] += 1
    rows = []
    for src, s in stats.items():
        snapshots_n = max(1, s["snapshots"]); settled = max(1, s["settled"])
        coverage = s["matched"] / snapshots_n; odds_coverage = s["odds"] / snapshots_n
        hit_rate = s["wins"] / settled; roi_signal = max(-0.2, min(0.2, s["profit"] / settled))
        clv = s["clv_sum"] / max(1, s["clv_n"]); uptime = s["health_active"] / max(1, s["health_total"])
        sample = min(1.0, (s["settled"] + s["snapshots"] / 20) / 150)
        raw = 0.35 * coverage + 0.15 * odds_coverage + 0.20 * uptime + 0.15 * (0.5 + roi_signal) + 0.15 * max(0, min(1, 0.5 + clv / 20))
        trust = 1.0 + (raw - 0.5) * sample
        trust_multiplier = round(max(0.65, min(1.20, trust)), 4)
        rows.append({
            "source_name": src, "trust_score": round(trust_multiplier * 100, 2),
            "success_rate": round(uptime * 100, 2), "avg_latency_ms": None,
            "roi_units": round(s["profit"], 3),
            "notes": f"settled={int(s['settled'])} snapshots={int(s['snapshots'])}",
            "raw": {"trust_multiplier": trust_multiplier, "snapshot_count": int(s["snapshots"]),
                    "settled_count": int(s["settled"]), "hit_rate": round(hit_rate, 4),
                    "avg_clv_pct": round(clv, 3), "matching_coverage": round(coverage, 4),
                    "odds_coverage": round(odds_coverage, 4), "uptime": round(uptime, 4)},
            "updated_at": now_iso(),
        })
    safe_json_write("prop_hunter_source_trust.json", rows)
    upsert_rows("prop_hunter_source_trust", rows, conflict="source_name")
    print(f"Source reliability: {len(rows)} source weights")
    return rows


if __name__ == "__main__":
    learn()
