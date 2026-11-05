"""Optional NBAstuffer / Databallr usage CSV imports.

No unsupported scraping or guessed player matching. These providers may change
schemas and access terms; accept only explicitly mapped, audited exports.
"""
import csv
import io
import math

PROVIDERS = frozenset({"nbastuffer", "databallr"})


def parse_provider_usage_csv(csv_text, provider, nba_ids_by_provider_id, season):
    """Read provider_player_id,player_name,usage_pct; USG% in 0..100 units."""
    if provider not in PROVIDERS:
        raise ValueError("unsupported usage provider")
    if not isinstance(season, str) or not season:
        raise ValueError("season required")
    reader = csv.DictReader(io.StringIO(csv_text))
    required = {"provider_player_id", "player_name", "usage_pct"}
    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        raise ValueError("export must be mapped to provider_player_id,player_name,usage_pct")
    output = {}
    for row in reader:
        external_id = (row.get("provider_player_id") or "").strip()
        if not external_id or external_id not in nba_ids_by_provider_id:
            continue
        try:
            player_id = int(nba_ids_by_provider_id[external_id])
            usage_pct = float(row["usage_pct"])
        except (ValueError, TypeError, KeyError):
            continue
        if player_id <= 0 or not math.isfinite(usage_pct) or not 0 <= usage_pct <= 100:
            continue
        if player_id in output:
            raise ValueError("ambiguous or duplicate canonical NBA player ID")
        output[player_id] = {
            "player_id": player_id, "player_name": row["player_name"],
            "usage_pct": usage_pct, "source": provider + "_csv",
            "scope": "season", "season": season,
        }
    return output
