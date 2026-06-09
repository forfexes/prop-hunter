"""Backtesting + reporting from picks_history.json."""
from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from ..config import CLV_HISTORY_FILE, PICKS_HISTORY_FILE
from ..logging_setup import get_logger

log = get_logger(__name__)


def _load(path: str) -> list:
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return []


def _summarise(picks: List[dict]) -> dict:
    if not picks:
        return {"n": 0, "wins": 0, "losses": 0, "winrate": 0.0, "roi": 0.0, "avg_odds": 0.0}
    settled = [p for p in picks if p.get("result") in ("win", "loss")]
    if not settled:
        return {"n": len(picks), "pending": len(picks), "wins": 0, "losses": 0,
                "winrate": 0.0, "roi": 0.0,
                "avg_odds": round(sum(p.get("odds", 0) for p in picks) / len(picks), 2)}
    wins = sum(1 for p in settled if p["result"] == "win")
    losses = len(settled) - wins
    total_stake = sum(p.get("stake", 1) for p in settled)
    profit = sum((p["odds"] - 1) * p["stake"] for p in settled if p["result"] == "win") \
             - sum(p["stake"] for p in settled if p["result"] == "loss")
    return {
        "n": len(settled), "wins": wins, "losses": losses,
        "winrate": round(100 * wins / len(settled), 1),
        "roi": round(100 * profit / total_stake, 1) if total_stake else 0.0,
        "avg_odds": round(sum(p["odds"] for p in settled) / len(settled), 2),
    }


def backtest(days: int = 30) -> str:
    history = _load(PICKS_HISTORY_FILE)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    rows: List[dict] = []
    for entry in history:
        if entry.get("date", "") < cutoff:
            continue
        rows.extend(entry.get("picks", []))
    if not rows:
        return f"No picks in last {days} days."
    by_sport: Dict[str, List[dict]] = defaultdict(list)
    by_market: Dict[str, List[dict]] = defaultdict(list)
    by_conf: Dict[str, List[dict]] = defaultdict(list)
    for p in rows:
        by_sport[p.get("sport", "?")].append(p)
        by_market[p.get("market", "?")].append(p)
        prob = p.get("probability") or 0
        bucket = f"{int(prob * 10) * 10}-{int(prob * 10) * 10 + 9}%" if prob else "?"
        by_conf[bucket].append(p)
    clv_rows = _load(CLV_HISTORY_FILE)
    clv_vals = [r["clv_pct"] for r in clv_rows if r.get("clv_pct") is not None]
    avg_clv = round(sum(clv_vals) / len(clv_vals), 2) if clv_vals else None
    lines = [f"# PropHunter Backtest — last {days} days", ""]
    overall = _summarise(rows)
    lines.append(f"**Overall:** {overall['n']} picks · "
                 f"{overall.get('wins',0)}-{overall.get('losses',0)} · "
                 f"WR {overall['winrate']}% · ROI {overall['roi']}% · avg odds {overall['avg_odds']}")
    if avg_clv is not None:
        lines.append(f"**Avg CLV:** {avg_clv}%")

    def section(title: str, groups: Dict[str, List[dict]]):
        lines.append(f"\n## {title}")
        for k, v in sorted(groups.items()):
            s = _summarise(v)
            lines.append(f"- **{k}**: n={s['n']}  WR {s['winrate']}%  ROI {s['roi']}%  avg @ {s['avg_odds']}")

    section("By Sport", by_sport)
    section("By Market", by_market)
    section("By Confidence Bucket", by_conf)
    return "\n".join(lines)
