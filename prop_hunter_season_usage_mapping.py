"""Fail-closed mapping of free NBA season data to canonical NBA player IDs.

Requires audited mapping keyed by source name, season, team, and player name.
Never fuzzy-match names or turn season usage into game L5/L10/L15.
"""
import math


def map_verified_season_usage(rows, mappings):
    """Return Supabase-ready records only for explicitly verified IDs.

    mappings: {(season, player_name, team): {"nba_player_id": int,
                                             "method": "verified_external_id"}}
    Ambiguous missing team mappings are not accepted.
    """
    out = []
    seen = set()
    for row in rows:
        season = row.get("season")
        name = row.get("player_name")
        team = row.get("team")
        mapping = mappings.get((season, name, team))
        if not isinstance(mapping, dict) or mapping.get("method") != "verified_external_id":
            continue
        player_id = mapping.get("nba_player_id")
        pct = row.get("usage_pct")
        if isinstance(player_id, bool) or not isinstance(player_id, int) or player_id <= 0:
            continue
        if not isinstance(pct, (float, int)) or isinstance(pct, bool) or not math.isfinite(pct) or not 0 <= pct <= 100:
            continue
        if row.get("scope") != "season" or row.get("source") != "boxscorelab_csv_cc_by_4_0":
            continue
        key = (player_id, season, row["source"])
        if key in seen:
            raise ValueError("duplicate player/season/source mapping; resolve traded-team rows")
        seen.add(key)
        out.append({"nba_player_id": player_id, "season": season,
                    "usage_pct": pct, "source": row["source"],
                    "source_player_name": name, "id_mapping_method": "verified_external_id"})
    return out
