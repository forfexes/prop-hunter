"""Validated Basketball-Reference season USG% CSV fallback.

This is an explicit CSV import adapter, NOT a live scraper. CSV must include
a verified NBA player ID supplied by an independent, audited ID mapping.
Never join production usage data on player name alone.
"""
import csv
import io
import math


def parse_bref_usage_csv(csv_text, nba_ids_by_bref_id):
    """Return season usage indexed by canonical NBA ID, rejecting ambiguous IDs."""
    rows = csv.DictReader(io.StringIO(csv_text))
    if not rows.fieldnames or not {"Player", "USG%"}.issubset(rows.fieldnames):
        raise ValueError("Basketball-Reference CSV requires Player and USG% columns")
    out = {}
    for row in rows:
        bref_id = (row.get("bref_id") or "").strip()
        if not bref_id or bref_id not in nba_ids_by_bref_id:
            continue
        try:
            nba_id = int(nba_ids_by_bref_id[bref_id])
            pct = float(row["USG%"])
        except (ValueError, TypeError, KeyError):
            continue
        if nba_id <= 0 or not math.isfinite(pct) or not 0 <= pct <= 100:
            continue
        if nba_id in out:
            raise ValueError(f"Duplicate NBA ID {nba_id}; resolve before import")
        out[nba_id] = {"player_id": nba_id, "player_name": row["Player"],
                       "usage_pct": pct, "source": "basketball_reference_csv",
                       "scope": "season"}
    return out
