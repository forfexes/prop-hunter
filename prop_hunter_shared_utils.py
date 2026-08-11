#!/usr/bin/env python3
"""
PROP HUNTER FINAL COVERAGE — SHARED UTILS
=========================================
Kleine gemeinsame Helper für Odds, Results, Settlement und Learning.
"""

from __future__ import annotations

import os
import re
import json
import time
import hashlib
from pathlib import Path
from datetime import datetime, timezone, date, timedelta
from typing import Any, Dict, List, Optional

import requests

try:
    from supabase import create_client
except Exception:
    create_client = None

TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "25"))

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()

def log(msg: str) -> None:
    print(msg, flush=True)

def warn(msg: str) -> None:
    print(f"WARNING: {msg}", flush=True)

def norm_name(s: Any) -> str:
    s = str(s or "").strip().lower()
    s = re.sub(r"[^a-z0-9\s\.\-']", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def norm_market(s: Any) -> str:
    s = str(s or "").strip().lower()
    s = s.replace("+", " plus ")
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def to_float(x: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if x is None or x == "":
            return default
        return float(str(x).replace("%", "").strip())
    except Exception:
        return default

def to_int(x: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        if x is None or x == "":
            return default
        return int(float(str(x).strip()))
    except Exception:
        return default

def safe_json_load(path: str | Path, default=None):
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default

def safe_json_write(path: str | Path, data: Any):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

def hash_key(*parts: Any) -> str:
    raw = "|".join(str(p or "") for p in parts)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()

def http_get(url: str, params=None, headers=None, retries: int = 2, sleep: float = 1.0):
    h = {
        "User-Agent": "PropHunterFinalCoverage/1.0",
        "Accept": "application/json,text/html,*/*",
    }
    if headers:
        h.update(headers)
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, params=params or {}, headers=h, timeout=TIMEOUT)
            if r.status_code in (401, 403, 404, 429):
                return r
            if r.status_code >= 500 and attempt < retries:
                time.sleep(sleep * (attempt + 1))
                continue
            return r
        except Exception as e:
            if attempt >= retries:
                warn(f"HTTP failed {url}: {e}")
                return None
            time.sleep(sleep * (attempt + 1))
    return None

def http_json(url: str, params=None, headers=None, retries: int = 2):
    r = http_get(url, params=params, headers=headers, retries=retries)
    if not r:
        return None
    if getattr(r, "status_code", 0) >= 400:
        warn(f"HTTP {r.status_code}: {url}")
        return None
    try:
        return r.json()
    except Exception as e:
        warn(f"JSON failed {url}: {e}")
        return None

def supabase_client():
    if create_client is None:
        return None
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    if not url or not key:
        return None
    try:
        return create_client(url, key)
    except Exception as e:
        warn(f"Supabase client failed: {e}")
        return None

def upsert_rows(table: str, rows: List[Dict[str, Any]], conflict: Optional[str] = None):
    if not rows:
        return
    sb = supabase_client()
    if sb is None:
        warn(f"Supabase missing; skip {table}: {len(rows)} rows")
        return
    try:
        q = sb.table(table).upsert(rows, on_conflict=conflict) if conflict else sb.table(table).insert(rows)
        q.execute()
        log(f"{table}: saved {len(rows)} rows")
    except Exception as e:
        warn(f"{table} save failed: {e}")

def select_rows(table: str, limit: int = 1000, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    sb = supabase_client()
    if sb is None:
        return []
    try:
        q = sb.table(table).select("*").limit(limit)
        for k, v in (filters or {}).items():
            q = q.eq(k, v)
        res = q.execute()
        return res.data or []
    except Exception as e:
        warn(f"{table} select failed: {e}")
        return []

def _normalise_pick_row(row: Dict[str, Any], source_table: str) -> Dict[str, Any]:
    """Return one schema-neutral pick row from either Supabase picks table."""
    out = dict(row or {})
    out["_source_table"] = source_table

    sent_date = out.get("sent_date") or out.get("date")
    if not sent_date and out.get("created_at"):
        sent_date = str(out.get("created_at"))[:10]
    if sent_date:
        out.setdefault("sent_date", sent_date)
        out.setdefault("date", sent_date)

    side = out.get("side") or out.get("direction")
    if side:
        out.setdefault("side", side)
        out.setdefault("direction", side)

    prob = out.get("prob") if out.get("prob") is not None else out.get("probability")
    if prob is not None:
        out.setdefault("prob", prob)
        out.setdefault("probability", prob)

    status = out.get("status") or out.get("result") or "pending"
    out.setdefault("status", status)
    out.setdefault("result", status)

    profit = out.get("profit_units") if out.get("profit_units") is not None else out.get("profit")
    if profit is not None:
        out.setdefault("profit_units", profit)
        out.setdefault("profit", profit)

    if not out.get("dedup_key"):
        out["dedup_key"] = hash_key(
            out.get("player") or out.get("player_name") or out.get("selection"),
            out.get("market") or out.get("prop_type"),
            out.get("line") or out.get("point"),
            side,
        )
    return out


def select_pick_rows(limit: int = 5000) -> List[Dict[str, Any]]:
    """Read and merge legacy ``prop_picks`` and modern ``prop_hunter_picks``.

    The project has used both schemas over time.  Reading only the first non-empty
    table silently hid historical picks, settlement and learning rows.  This helper
    normalises both tables and deduplicates by date + dedup key.
    """
    merged: Dict[str, Dict[str, Any]] = {}
    for table in ("prop_hunter_picks", "prop_picks"):
        for raw in select_rows(table, limit=limit):
            row = _normalise_pick_row(raw, table)
            date_key = str(row.get("sent_date") or row.get("date") or "")
            key = f"{date_key}|{row.get('dedup_key')}"
            current = merged.get(key)
            if current is None:
                row["_source_tables"] = [table]
                merged[key] = row
                continue

            # Preserve the richest representation while preferring a settled status.
            for field, value in row.items():
                if field.startswith("_"):
                    continue
                if current.get(field) in (None, "", [], {}) and value not in (None, "", [], {}):
                    current[field] = value
            incoming_status = str(row.get("status") or row.get("result") or "pending").lower()
            current_status = str(current.get("status") or current.get("result") or "pending").lower()
            if current_status in ("", "pending", "open", "unsettled") and incoming_status not in ("", "pending", "open", "unsettled"):
                current["status"] = incoming_status
                current["result"] = incoming_status
                if row.get("profit_units") is not None or row.get("profit") is not None:
                    profit = row.get("profit_units") if row.get("profit_units") is not None else row.get("profit")
                    current["profit_units"] = profit
                    current["profit"] = profit
            tables = current.setdefault("_source_tables", [])
            if table not in tables:
                tables.append(table)

    return sorted(
        merged.values(),
        key=lambda row: str(row.get("sent_date") or row.get("date") or row.get("created_at") or ""),
        reverse=True,
    )[:limit]


def pick_id(row: Dict[str, Any]) -> str:
    return str(row.get("pick_id") or row.get("id") or row.get("row_hash") or row.get("selection_id") or hash_key(row))

def implied_prob(decimal_odds: Any) -> Optional[float]:
    odds = to_float(decimal_odds)
    if not odds or odds <= 1:
        return None
    return 1.0 / odds

def american_to_decimal(x: Any) -> Optional[float]:
    v = to_float(x)
    if v is None:
        return None
    if v > 0:
        return 1 + v / 100.0
    if v < 0:
        return 1 + 100.0 / abs(v)
    return None
