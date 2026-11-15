#!/usr/bin/env python3
"""ESPN box-score fallback for settlement (keyless).

Prop Hunter grades against the primary stat sources (nba_api, the NHL/NFL/MLB
collectors) written into prop_hunter_player_gamelogs. When a player's gamelog is
missing there — because a quote feed attached the player to the wrong game, the
game_id never resolved, or the primary API was flaky — the pick stays pending
forever and eventually gets voided P/L-neutral.

This module is a SECOND source for exactly that case, borrowed from NETRATTLER's
multi-source ResultResolver pattern: for a player + date it pulls the box score
from ESPN's public site API and returns their stat line, so a pick that the
primary source could not grade can still be settled against a real number
instead of being thrown away.

Keyless, read-only, fail-soft: any error returns None and the caller keeps its
existing behaviour. Gated via PH_ESPN_FALLBACK (default on).
"""
from __future__ import annotations
import os
import datetime as _dt
from typing import Any, Dict, List, Optional

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

# ESPN site API: sport path + league id per Prop Hunter sport label.
ESPN_PATHS = {
    "NBA": ("basketball", "nba"),
    "WNBA": ("basketball", "wnba"),
    "NFL": ("football", "nfl"),
    "NHL": ("hockey", "nhl"),
    "MLB": ("baseball", "mlb"),
    "NCAAB": ("basketball", "mens-college-basketball"),
    "NCAAF": ("football", "college-football"),
}

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
       "Referer": "https://www.espn.com/"}

# Map ESPN box-score stat labels to Prop Hunter canonical stat keys. ESPN labels
# vary by sport; the matcher below is substring/alias based so new labels degrade
# gracefully rather than crash.
_STAT_ALIASES = {
    "points": ("points", "pts"),
    "rebounds": ("rebounds", "reb", "totreb"),
    "assists": ("assists", "ast"),
    "steals": ("steals", "stl"),
    "blocks": ("blocks", "blk"),
    "threes": ("3pt", "threes", "3-pointers", "fg3"),
    "turnovers": ("turnovers", "to"),
    # NHL
    "shots_on_goal": ("shots", "sog", "shots on goal"),
    "goals": ("goals", "g"),
    "saves": ("saves", "sv"),
    # NFL
    "passing_yards": ("passingyards", "passing yards", "yds"),
    "rushing_yards": ("rushingyards", "rushing yards"),
    "receiving_yards": ("receivingyards", "receiving yards"),
    "receptions": ("receptions", "rec"),
}

_ENABLED = os.getenv("PH_ESPN_FALLBACK", "1").lower() in {"1", "true", "yes", "on"}
_TIMEOUT = float(os.getenv("PH_ESPN_TIMEOUT", "10"))
_scoreboard_cache: Dict[str, Any] = {}


def _norm(s: Any) -> str:
    import unicodedata
    n = unicodedata.normalize("NFKD", str(s or "").lower().strip())
    n = "".join(c for c in n if not unicodedata.combining(c))
    for ch in ".,'`-":
        n = n.replace(ch, "")
    return " ".join(n.split())


def _date_variants(target: str) -> List[str]:
    """ESPN scoreboard expects YYYYMMDD; accept a few input shapes."""
    t = str(target or "")[:10]
    try:
        d = _dt.date.fromisoformat(t)
    except ValueError:
        return []
    return [d.strftime("%Y%m%d")]


def _scoreboard(sport: str, league: str, yyyymmdd: str) -> Optional[dict]:
    if requests is None:
        return None
    key = f"{league}:{yyyymmdd}"
    if key in _scoreboard_cache:
        return _scoreboard_cache[key]
    url = f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard"
    try:
        r = requests.get(url, params={"dates": yyyymmdd}, headers=_UA, timeout=_TIMEOUT)
        data = r.json() if r.ok else None
    except Exception:
        data = None
    _scoreboard_cache[key] = data
    return data


def _summary(sport: str, league: str, event_id: str) -> Optional[dict]:
    if requests is None:
        return None
    url = f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/summary"
    try:
        r = requests.get(url, params={"event": event_id}, headers=_UA, timeout=_TIMEOUT)
        return r.json() if r.ok else None
    except Exception:
        return None


def _final_event_ids(sb: dict) -> List[str]:
    ids = []
    for ev in (sb or {}).get("events", []) or []:
        st = (((ev.get("status") or {}).get("type") or {}).get("name") or "")
        if st in ("STATUS_FINAL", "STATUS_FULL_TIME", "STATUS_FINAL_OT"):
            ids.append(str(ev.get("id")))
    return ids


def _athlete_stats(summary: dict, player_norm: str) -> Optional[Dict[str, float]]:
    """Pull one athlete's stat line from an ESPN summary box score."""
    box = (summary or {}).get("boxscore", {}) or {}
    for team in box.get("players", []) or []:
        for group in team.get("statistics", []) or []:
            labels = [str(x) for x in (group.get("labels") or group.get("names") or [])]
            for ath in group.get("athletes", []) or []:
                info = ath.get("athlete", {}) or {}
                nm = _norm(info.get("displayName") or info.get("shortName"))
                if nm != player_norm:
                    continue
                vals = ath.get("stats") or []
                out: Dict[str, float] = {}
                for lab, val in zip(labels, vals):
                    lab_l = _norm(lab)
                    for canon, aliases in _STAT_ALIASES.items():
                        if any(a in lab_l or lab_l == _norm(a) for a in aliases):
                            try:
                                # ESPN sometimes gives "7-12" style combos; take first int.
                                out[canon] = float(str(val).split("-")[0].split("/")[0])
                            except (ValueError, TypeError):
                                pass
                            break
                if out:
                    return out
    return None


def espn_player_statline(player: str, sport: str, target_date: str) -> Optional[Dict[str, float]]:
    """Return {canonical_stat: value} for a player on a date, or None.

    Only returns a line when the player appears in exactly one FINAL game that
    day (a player plays one game per day), matching the primary settler's
    single-match safety rule.
    """
    if not _ENABLED:
        return None
    paths = ESPN_PATHS.get(str(sport or "").upper())
    if not paths:
        return None
    sport_path, league = paths
    player_norm = _norm(player)
    for ymd in _date_variants(target_date):
        sb = _scoreboard(sport_path, league, ymd)
        if not sb:
            continue
        hits = []
        for ev_id in _final_event_ids(sb):
            summ = _summary(sport_path, league, ev_id)
            line = _athlete_stats(summ, player_norm) if summ else None
            if line:
                hits.append(line)
            if len(hits) > 1:
                return None  # ambiguous — stay safe
        if len(hits) == 1:
            return hits[0]
    return None


if __name__ == "__main__":
    import sys, json
    if len(sys.argv) >= 4:
        print(json.dumps(espn_player_statline(sys.argv[1], sys.argv[2], sys.argv[3]), indent=2))
    else:
        print("usage: prop_hunter_espn_boxscore.py '<player>' <SPORT> <YYYY-MM-DD>")
