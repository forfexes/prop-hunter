"""Import verified free NBA season CSV into isolated Supabase staging.

No NBA ID claims, no game-level L10/L15 contamination. Requires server-side
SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY; never logs credentials.
"""
import json
import os
from urllib.request import Request, urlopen
from prop_hunter_boxscorelab import download_season_csv, parse_season_csv

SEASONS = ("2026-27", "2025-26", "2024-25", "2023-24", "2022-23")


def make_records(season, csv_text):
    rows = parse_season_csv(csv_text, season)
    if not rows:
        raise ValueError("empty season " + season)
    return [{"season": r["season"], "player_name": r["player_name"],
             "team": r["team"], "usage_pct": r["usage_pct"],
             "games": r["games"], "source": r["source"]} for r in rows]


def upload(records, url, key, post=None):
    if not records:
        return 0
    if not url.startswith("https://") or not key:
        raise ValueError("secure Supabase credentials required")
    endpoint = url.rstrip("/") + "/rest/v1/prop_hunter_nba_season_usage_staging?on_conflict=season,player_name,team,source"
    sender = post or urlopen
    for offset in range(0, len(records), 100):
        chunk = records[offset:offset+100]
        req = Request(endpoint, data=json.dumps(chunk, allow_nan=False).encode(),
                      headers={"apikey": key, "Authorization": "Bearer " + key,
                               "Content-Type": "application/json",
                               "Prefer": "resolution=merge-duplicates,return=minimal"}, method="POST")
        with sender(req, timeout=30) as response:
            if response.status not in (200, 201, 204):
                raise RuntimeError("Supabase upsert failed")
    return len(records)


def main():
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        print("NBA season staging: credentials unavailable; no writes")
        return 0
    total = 0
    for season in SEASONS:
        records = make_records(season, download_season_csv(season))
        count = upload(records, url, key)
        total += count
        print("NBA season staging:", season, count, "verified season rows")
    print("NBA season staging total:", total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
