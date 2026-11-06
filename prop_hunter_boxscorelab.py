"""BoxScore Lab public CSV reader: verified season-only metrics, never game USG form.

Source: https://www.boxscorelab.com/downloads/ (CC BY 4.0, attribution required).
No player-name joining into production IDs, no synthetic missing data.
"""
import csv
import io
import math
import urllib.request

BASE = "https://www.boxscorelab.com/downloads/"
VALID_SEASONS = frozenset(("2022-23", "2023-24", "2024-25", "2025-26", "2026-27"))


def download_season_csv(season, timeout=15):
    if season not in VALID_SEASONS:
        raise ValueError("unsupported season")
    url = BASE + season + "-player-season-totals.csv"
    request = urllib.request.Request(url, headers={"User-Agent": "PropHunterSourceCheck/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read(4_000_001)
    if len(raw) > 4_000_000:
        raise ValueError("source file too large")
    return raw.decode("utf-8-sig")


def parse_season_csv(csv_text, season):
    """Produce provenance-rich season records, not NBA-ID-keyed features."""
    if season not in VALID_SEASONS:
        raise ValueError("unsupported season")
    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames:
        raise ValueError("missing CSV header")
    headers = {h.strip().lower().replace("_", "").replace(" ", ""): h for h in reader.fieldnames if h}
    def column(*aliases):
        return next((headers[a] for a in aliases if a in headers), None)
    usage = column("usg%", "usg", "usagerate", "usagepct", "usage")
    player = column("player", "playername", "name")
    if not usage or not player:
        raise ValueError("missing explicit player/usage columns: " + ",".join(reader.fieldnames))
    games = column("gp", "games", "gamesplayed")
    season_field = column("season")
    rows = []
    seen = set()
    for r in reader:
        name = str(r.get(player) or "").strip()
        raw = str(r.get(usage) or "").strip().rstrip("%")
        if not name or not raw:
            continue
        try:
            value = float(raw)
        except ValueError:
            continue
        if not math.isfinite(value) or value < 0:
            continue
        # Source publishes rates as decimal fractions; explicit percent columns are percent units.
        rate_fraction = "%" not in usage and usage.lower().replace("_", "") in ("usagerate", "usage")
        pct = value * 100 if rate_fraction and value <= 1 else value
        if not 0 <= pct <= 100:
            continue
        if season_field and str(r.get(season_field) or "").strip() not in (season, season.replace("-", "")):
            continue
        if games:
            try:
                count = int(float(r.get(games) or 0))
            except ValueError:
                continue
            if count <= 0:
                continue
        else:
            count = None
        # The CSV can contain multiple teams per player; retain rows for review, but do not ID-join.
        key = (name, str(r.get("team") or ""), season)
        if key in seen:
            raise ValueError("duplicate source player/team/season row")
        seen.add(key)
        rows.append({"player_name": name, "season": season, "usage_pct": pct,
                     "games": count, "scope": "season",
                     "source": "boxscorelab_csv_cc_by_4_0",
                     "attribution": "BoxScore Lab, https://boxscorelab.com"})
    return rows


def source_check(season):
    csv_text = download_season_csv(season)
    rows = parse_season_csv(csv_text, season)
    if not rows:
        raise ValueError("no verified season usage rows")
    return {"source": "BoxScore Lab", "season": season, "rows": len(rows),
            "scope": "season", "usable_for_l10_l15": False,
            "header": next(csv.reader(io.StringIO(csv_text))),
            "sample_usage_pct": [r["usage_pct"] for r in rows[:3]]}


if __name__ == "__main__":
    import json
    print(json.dumps(source_check("2026-27"), sort_keys=True))
