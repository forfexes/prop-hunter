#!/usr/bin/env python3
"""Free, keyless data sources for Prop Hunter (no heavy packages, no API keys).

Pulls the same data the SportsDataverse/nflverse packages expose, but directly
from their public GitHub CSV releases — so there is no multi-minute pip install
and nothing to break in CI. GitHub is on the allowlist, so these work from the
sandbox and from Actions.

Current feeds:
  injuries   nflverse NFL injury reports (Out/Doubtful/Questionable per week)
             -> feeds the "player X is out, his targets free up" edge.

Everything is fail-soft and cached per run. More feeds (hoopR boxscores,
fastRhockey, MoneyPuck xG) can be added the same way.
"""
from __future__ import annotations
import csv
import io
import os
from datetime import date

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

_TIMEOUT = float(os.getenv("PH_FREE_DATA_TIMEOUT", "20"))
_cache: dict = {}


def _norm(s) -> str:
    import unicodedata
    n = unicodedata.normalize("NFKD", str(s or "").lower().strip())
    n = "".join(c for c in n if not unicodedata.combining(c))
    for ch in ".,'`-":
        n = n.replace(ch, "")
    return " ".join(n.split())


def _current_nfl_season() -> int:
    t = date.today()
    # NFL season spans Sep–Feb; Jan/Feb still belong to the prior year's season.
    return t.year if t.month >= 3 else t.year - 1


def nfl_injuries(season: int = None) -> list:
    """nflverse injury report rows for a season (list of dicts), or []."""
    if requests is None:
        return []
    season = season or _current_nfl_season()
    key = f"nfl_injuries_{season}"
    if key in _cache:
        return _cache[key]
    url = (f"https://github.com/nflverse/nflverse-data/releases/download/"
           f"injuries/injuries_{season}.csv")
    try:
        r = requests.get(url, timeout=_TIMEOUT)
        rows = list(csv.DictReader(io.StringIO(r.text))) if r.ok else []
    except Exception:
        rows = []
    _cache[key] = rows
    return rows


def nfl_out_players(season: int = None, week: int = None,
                    statuses=("Out", "Doubtful")) -> dict:
    """{normalized_name: {team, position, status, injury}} for the latest (or
    given) week — the players who will miss or likely miss the game.
    """
    rows = nfl_injuries(season)
    if not rows:
        return {}
    weeks = [int(r["week"]) for r in rows if r.get("week", "").isdigit()]
    if not weeks:
        return {}
    wk = week or max(weeks)
    out = {}
    for r in rows:
        if r.get("week") != str(wk):
            continue
        if r.get("report_status") not in statuses:
            continue
        nm = r.get("full_name") or f"{r.get('first_name','')} {r.get('last_name','')}"
        nm = nm.strip()
        if not nm:
            continue
        out[_norm(nm)] = {
            "team": r.get("team"), "position": r.get("position"),
            "status": r.get("report_status"),
            "injury": r.get("report_primary_injury"),
            "name": nm,
        }
    return out


def is_player_out_nfl(player: str, season: int = None, week: int = None) -> dict:
    """Return the injury record for a player if Out/Doubtful, else {}."""
    return nfl_out_players(season, week).get(_norm(player), {})


def team_outs_nfl(team_abbrev: str, season: int = None, week: int = None) -> list:
    """All Out/Doubtful players for a team this week — the teammates whose usage
    gets redistributed (the VanVleet/Smart case)."""
    outs = nfl_out_players(season, week)
    ab = str(team_abbrev or "").upper()
    return [v for v in outs.values() if str(v.get("team", "")).upper() == ab]


if __name__ == "__main__":
    import json
    outs = nfl_out_players()
    print(f"NFL out/doubtful this week: {len(outs)}")
    print(json.dumps(list(outs.values())[:8], indent=2))
