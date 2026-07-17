#!/usr/bin/env python3
"""Learns empirical pair factors for PROP HUNTER builders.

The output is intentionally conservative: factors are shrunk toward 1.0 and clipped.
They are used only after enough settled same-event observations exist.
"""
from __future__ import annotations

import itertools
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from prop_hunter_shared_utils import safe_json_load, safe_json_write, select_rows

OUT = Path(os.getenv("PH_BUILDER_CORRELATIONS_FILE", "prop_hunter_builder_correlations.json"))
HISTORY = Path(os.getenv("PH_HISTORY_FILE", "picks_history.json"))
MIN_PAIR_SAMPLES = int(os.getenv("PH_MIN_PAIR_SAMPLES", "12"))


def market_group(text: Any) -> str:
    s = re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()
    for needles, label in (
        (("home run", "homer"), "home_runs"), (("strikeout",), "strikeouts"),
        (("hits runs rbi", "h r rbi"), "hrr"), (("total bases",), "total_bases"),
        (("hits",), "hits"), (("points rebounds assists", "pra"), "pra"),
        (("points rebounds",), "points_rebounds"), (("points assists",), "points_assists"),
        (("rebounds assists",), "rebounds_assists"), (("3 pt", "three", "3pm"), "threes"),
        (("points",), "points"), (("rebounds",), "rebounds"), (("assists",), "assists"),
        (("passing",), "passing"), (("rushing",), "rushing"),
        (("receiving", "reception"), "receiving"), (("touchdown",), "touchdowns"),
        (("shots",), "shots"),
    ):
        if any(n in s for n in needles): return label
    return s[:35].replace(" ", "_") or "other"


def _canonical(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    raw = row.get("pick_raw") if isinstance(row.get("pick_raw"), dict) else {}
    result = str(row.get("result") or raw.get("result") or "").lower()
    if result not in {"win", "loss", "won", "lost", "hit", "miss"}: return None
    sport = str(row.get("sport") or row.get("league") or raw.get("sport") or "UNKNOWN").upper()
    market = row.get("market") or row.get("market_key") or raw.get("market") or "other"
    direction = str(row.get("direction") or raw.get("direction") or "over").lower()
    event = str(row.get("event_id") or row.get("game_id") or raw.get("game_id") or raw.get("game") or "")
    date = str(row.get("event_date") or row.get("date") or row.get("created_at") or raw.get("date") or "")[:10]
    player = str(row.get("player_name") or row.get("player") or raw.get("player") or "")
    return {
        "sport": sport, "market_group": market_group(market), "direction": direction,
        "event": event or f"{sport}:{date}", "date": date, "player": player,
        "win": 1 if result in {"win", "won", "hit"} else 0,
    }


def load_rows(limit: int = 10000) -> List[Dict[str, Any]]:
    raw = select_rows("prop_hunter_results", limit=limit)
    history = safe_json_load(HISTORY, {}) or {}
    for day in history.values() if isinstance(history, dict) else []:
        if isinstance(day, dict): raw.extend(day.get("picks", []) or [])
    return [x for x in (_canonical(r) for r in raw) if x]


def pair_key(a: str, b: str) -> str:
    return "|".join(sorted((a, b)))


def learn() -> Dict[str, Any]:
    rows = load_rows()
    groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for row in rows: groups[(row["sport"], row["event"])].append(row)
    counts: Dict[str, Dict[str, float]] = defaultdict(lambda: {"n": 0, "a": 0, "b": 0, "joint": 0})
    for (sport, _), event_rows in groups.items():
        # One observation per market/direction/player to avoid old duplicates.
        unique = {}
        for row in event_rows:
            unique[(row["player"].lower(), row["market_group"], row["direction"])] = row
        vals = list(unique.values())[:40]
        for a, b in itertools.combinations(vals, 2):
            if a["player"].lower() == b["player"].lower() and a["market_group"] == b["market_group"]:
                continue
            la = f"{sport}:{a['market_group']}:{a['direction']}"
            lb = f"{sport}:{b['market_group']}:{b['direction']}"
            key = pair_key(la, lb); c = counts[key]
            c["n"] += 1; c["a"] += a["win"]; c["b"] += b["win"]; c["joint"] += a["win"] * b["win"]
    pairs = {}
    for key, c in counts.items():
        n = int(c["n"])
        if n < MIN_PAIR_SAMPLES: continue
        pa = (c["a"] + 2) / (n + 4); pb = (c["b"] + 2) / (n + 4)
        pj = (c["joint"] + 1) / (n + 2)
        raw_factor = pj / max(0.01, pa * pb)
        shrink = n / (n + 40)
        factor = 1.0 + (raw_factor - 1.0) * shrink
        pairs[key] = {
            "n": n, "p_a": round(pa, 4), "p_b": round(pb, 4), "p_joint": round(pj, 4),
            "factor": round(max(0.80, min(1.20, factor)), 4),
        }
    payload = {"updated_at": datetime.now(timezone.utc).isoformat(), "rows": len(rows), "pairs": pairs}
    safe_json_write(OUT, payload)
    print(f"Builder learning: rows={len(rows)} pair_models={len(pairs)}")
    return payload


if __name__ == "__main__":
    learn()
