"""Explicit NBA usage ingest: official game endpoint -> validated Supabase upsert.

Usage: python prop_hunter_nba_usage_ingest.py 0022600001 2026-10-28
Requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY; never logs credentials.
No writes when the official endpoint returns no valid observations.
"""
import os
import sys
from urllib.parse import urlparse
from prop_hunter_nba_usage import safe_fetch_game_usage


def upsert_official_game_usage(rows, *, url, service_key, post=None):
    if not rows:
        return 0
    if not service_key or not url:
        raise ValueError("Supabase credentials are required")
    if urlparse(url).scheme != "https":
        raise ValueError("Supabase URL must be HTTPS")
    from urllib.request import Request, urlopen
    import json
    records = []
    seen = set()
    for row in rows:
        if row.get("source") != "nba_official_boxscore_usage_v3" or row.get("scope") != "game":
            raise ValueError("only verified official game usage is accepted")
        player_id = int(row["player_id"])
        game_id = str(row["game_id"])
        pct = float(row["usage_pct"])
        from datetime import date
        date.fromisoformat(row["game_date"])
        if player_id <= 0 or len(game_id) != 10 or not game_id.isdigit() or not 0 <= pct <= 100:
            raise ValueError("invalid game usage observation")
        key = (player_id, game_id)
        if key in seen:
            raise ValueError("duplicate player/game in payload")
        seen.add(key)
        records.append({"nba_player_id": player_id, "nba_game_id": game_id,
                        "game_date": row["game_date"], "usage_pct": pct,
                        "source": row["source"]})
    endpoint = url.rstrip("/") + "/rest/v1/prop_hunter_nba_game_usage?on_conflict=nba_player_id,nba_game_id"
    headers = {"apikey": service_key, "Authorization": "Bearer " + service_key,
               "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates,return=minimal"}
    request = Request(endpoint, data=json.dumps(records).encode(), headers=headers, method="POST")
    if post is not None:
        post(request)
    else:
        with urlopen(request, timeout=20) as response:
            if response.status not in (200, 201, 204):
                raise RuntimeError("Supabase usage upsert failed")
    return len(records)


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        raise SystemExit("Usage: python prop_hunter_nba_usage_ingest.py NBA_GAME_ID YYYY-MM-DD")
    rows = safe_fetch_game_usage(args[0], args[1])
    if not rows:
        print("NBA game usage UNAVAILABLE: zero rows written")
        return 0
    count = upsert_official_game_usage(rows, url=os.environ.get("SUPABASE_URL"),
                                      service_key=os.environ.get("SUPABASE_SERVICE_ROLE_KEY"))
    print(f"NBA game usage: {count} verified observations written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
