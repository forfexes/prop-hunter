"""Read verified NBA USG% form from Supabase, keyed ONLY by canonical NBA ID.

Optional feature enrichment. Missing data and incomplete windows stay None.
No name-based join, no season-to-game substitution.
"""
import math


def attach_nba_usage_form(feature, nba_player_id, usage_by_id):
    enriched = dict(feature)
    if nba_player_id is None:
        return enriched
    try:
        key = int(nba_player_id)
    except (TypeError, ValueError):
        return enriched
    row = usage_by_id.get(key)
    if not row:
        return enriched
    for n in (5, 10, 15):
        count = row.get(f"l{n}_observed")
        value = row.get(f"usage_l{n}")
        try:
            count = int(count)
            value = float(value)
        except (TypeError, ValueError):
            continue
        if count == n and math.isfinite(value) and 0 <= value <= 100:
            enriched[f"nba_usage_l{n}"] = value
            enriched[f"nba_usage_l{n}_source"] = "nba_official_boxscore_usage_v3"
    return enriched


def load_nba_usage_form(client, page_size=1000):
    """Optional read-only projection, with pagination and canonical IDs."""
    if client is None:
        return {}
    output = {}
    last_id = 0
    while True:
        response = (client.table("prop_hunter_nba_usage_form")
                    .select("*").gt("nba_player_id", last_id)
                    .order("nba_player_id").limit(page_size).execute())
        rows = response.data or []
        if not rows:
            break
        for row in rows:
            key = int(row["nba_player_id"])
            if key <= last_id:
                raise ValueError("NBA usage form pagination did not advance")
            output[key] = row
        last_id = max(output)
        if len(rows) < page_size:
            break
    return output
