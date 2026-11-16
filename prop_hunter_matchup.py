#!/usr/bin/env python3
"""Opponent-defense matchup ratings, all sports, keyless (JK-style edge).

JK's edge isn't a secret feed — it's combining a player's recent hit rate with
the OPPONENT DEFENSE matchup ("Washington allows the 2nd-most rebounds"). This
module computes, per sport, how much each team's defense allows in each stat
category, ranked league-wide, from ESPN's public team-statistics endpoint
(keyless). A pick then gets a matchup_rating: how favourable the opponent is
for that player's stat.

Categories per sport mirror what the books price:
  NBA/WNBA : points, rebounds, assists, threes  (opponent allowed)
  NHL      : shots, goals, assists              (opponent allowed)
  NFL      : passing_yards, rushing_yards, receiving_yards
  MLB      : hits, strikeouts, runs

Rating scale (what we attach to a pick):
  rank 1  = opponent allows the MOST of this stat  -> best matchup for an OVER
  rank 30 = opponent allows the least              -> worst for an OVER
We expose both the raw league rank and a normalized 0..1 "over_friendliness"
(1 = softest defense). For an UNDER pick the favourability is inverted.

Fail-soft: any error -> empty ratings, callers keep working. Cached per run.
"""
from __future__ import annotations
import os
from typing import Dict, Optional

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

# Prop Hunter sport -> (espn_sport_path, espn_league)
ESPN_LEAGUE = {
    "NBA": ("basketball", "nba"),
    "WNBA": ("basketball", "wnba"),
    "NHL": ("hockey", "nhl"),
    "NFL": ("football", "nfl"),
    "MLB": ("baseball", "mlb"),
}

# Prop Hunter stat key -> ESPN opponent-stat name fragments to match (lowercased
# substring match against ESPN's stat "name"/"displayName"). We read the
# opponent/against split so a high value = a defense that ALLOWS a lot.
STAT_MATCH = {
    "NBA": {
        "points": ("points",), "rebounds": ("rebounds",),
        "assists": ("assists",), "threes": ("threepointfieldgoalsmade", "3pt"),
    },
    "WNBA": {
        "points": ("points",), "rebounds": ("rebounds",),
        "assists": ("assists",), "threes": ("threepointfieldgoalsmade", "3pt"),
    },
    "NHL": {
        "shots_on_goal": ("shotstotal", "shots"), "goals": ("goals",),
        "assists": ("assists",),
    },
    "NFL": {
        "passing_yards": ("passingyards", "netpassingyards"),
        "rushing_yards": ("rushingyards",),
        "receiving_yards": ("receivingyards", "passingyards"),
    },
    "MLB": {
        "hits": ("hits",), "strikeouts": ("strikeouts",), "runs": ("runs",),
    },
}

_TIMEOUT = float(os.getenv("PH_MATCHUP_TIMEOUT", "12"))
_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}
_ENABLED = os.getenv("PH_MATCHUP_ENABLED", "1").lower() in {"1", "true", "yes", "on"}
_cache: Dict[str, dict] = {}


def _norm(s) -> str:
    return "".join(ch for ch in str(s or "").lower() if ch.isalnum())


# Team-Nickname/Stadt -> offizielle Abkuerzung (nba_api / ESPN). Das Matching
# laeuft ueber _norm, also genuegen Nickname ODER Stadt. Kritisch, weil die
# 3-Buchstaben-Heuristik sonst ROC statt HOU, WIZ statt WAS liefert.
TEAM_ABBR = {
    # NBA
    "hawks": "ATL", "atlanta": "ATL", "celtics": "BOS", "boston": "BOS",
    "nets": "BKN", "brooklyn": "BKN", "hornets": "CHA", "charlotte": "CHA",
    "bulls": "CHI", "chicago": "CHI", "cavaliers": "CLE", "cavs": "CLE", "cleveland": "CLE",
    "mavericks": "DAL", "mavs": "DAL", "dallas": "DAL", "nuggets": "DEN", "denver": "DEN",
    "pistons": "DET", "detroit": "DET", "warriors": "GSW", "goldenstate": "GSW",
    "rockets": "HOU", "houston": "HOU", "pacers": "IND", "indiana": "IND",
    "clippers": "LAC", "lakers": "LAL", "grizzlies": "MEM", "memphis": "MEM",
    "heat": "MIA", "miami": "MIA", "bucks": "MIL", "milwaukee": "MIL",
    "timberwolves": "MIN", "wolves": "MIN", "minnesota": "MIN",
    "pelicans": "NOP", "neworleans": "NOP", "knicks": "NYK", "newyork": "NYK",
    "thunder": "OKC", "oklahomacity": "OKC", "magic": "ORL", "orlando": "ORL",
    "sixers": "PHI", "76ers": "PHI", "philadelphia": "PHI", "philadelphia76ers": "PHI",
    "suns": "PHX", "phoenix": "PHX", "trailblazers": "POR", "blazers": "POR", "portland": "POR",
    "kings": "SAC", "sacramento": "SAC", "spurs": "SAS", "sanantonio": "SAS",
    "raptors": "TOR", "toronto": "TOR", "jazz": "UTA", "utah": "UTA",
    "wizards": "WAS", "washington": "WAS",
}


def team_abbr(team: str) -> str:
    """Offizielle Team-Abkuerzung aus einem Namen (nickname oder stadt)."""
    t = str(team or "").strip()
    if not t:
        return ""
    n = _norm(t)
    if n in TEAM_ABBR:
        return TEAM_ABBR[n]
    # einzelne Worte durchprobieren (letztes zuerst = meist der Nickname)
    for w in reversed(t.split()):
        wn = _norm(w)
        if wn in TEAM_ABBR:
            return TEAM_ABBR[wn]
    # Fallback: erste 3 Grossbuchstaben des letzten Wortes
    return t.split()[-1].upper()[:3]


def _fetch_nba_defense_nbaapi(sport: str) -> Dict[str, Dict[str, float]]:
    """NBA/WNBA opponent defense via nba_api LeagueDashTeamStats (Opponent).

    The reliable source for per-team opponent-allowed stats. Returns
    {TEAM_ABBR: {points/rebounds/assists/threes: allowed_per_game}}.
    """
    try:
        from nba_api.stats.endpoints import leaguedashteamstats
        from nba_api.stats.static import teams as nba_teams
    except Exception:
        return {}
    season = os.getenv("PH_NBA_SEASON") or _current_nba_season()
    league_id = "10" if sport.upper() == "WNBA" else "00"
    try:
        res = leaguedashteamstats.LeagueDashTeamStats(
            measure_type_detailed_defense="Opponent",
            per_mode_detailed="PerGame",
            season=season,
            league_id_nullable=league_id,
            timeout=_TIMEOUT,
        )
        rows = res.get_normalized_dict().get("LeagueDashTeamStats", [])
    except Exception as e:
        print(f"matchup: nba_api failed: {type(e).__name__}: {str(e)[:120]}", flush=True)
        return {}
    id_to_abbr = {t["id"]: t["abbreviation"] for t in nba_teams.get_teams()}
    out: Dict[str, Dict[str, float]] = {}
    for r in rows:
        tid = r.get("TEAM_ID")
        ab = id_to_abbr.get(tid) or (str(r.get("TEAM_NAME", "")).split()[-1][:3].upper())
        bag = {}
        for stat_key, col in (("points", "OPP_PTS"), ("rebounds", "OPP_REB"),
                              ("assists", "OPP_AST"), ("threes", "OPP_FG3M")):
            v = r.get(col)
            if v is not None:
                try:
                    bag[stat_key] = float(v)
                except (TypeError, ValueError):
                    pass
        if bag:
            out[str(ab).upper()] = bag
    return out


def _current_nba_season() -> str:
    import datetime as _d
    now = _d.date.today()
    start = now.year if now.month >= 10 else now.year - 1
    return f"{start}-{str(start + 1)[2:]}"


def _fetch_standings_points(sport: str) -> Dict[str, Dict[str, float]]:
    """Fallback: ESPN standings -> points allowed per game (keyless)."""
    paths = ESPN_LEAGUE.get(sport.upper())
    if requests is None or not paths:
        return {}
    url = f"https://site.api.espn.com/apis/v2/sports/{paths[0]}/{paths[1]}/standings"
    try:
        r = requests.get(url, headers=_UA, timeout=_TIMEOUT)
        data = r.json() if r.ok else {}
    except Exception as e:
        print(f"matchup: standings failed: {type(e).__name__}", flush=True)
        return {}
    out: Dict[str, Dict[str, float]] = {}

    def walk(node):
        if isinstance(node, dict):
            for ent in node.get("standings", {}).get("entries", []) if isinstance(node.get("standings"), dict) else []:
                ab = (ent.get("team") or {}).get("abbreviation")
                st = {x.get("name"): x.get("value") for x in ent.get("stats", [])}
                pa = st.get("avgPointsAgainst")
                if pa is None:
                    pa = st.get("pointsAgainst")
                    gp = st.get("gamesPlayed")
                    if pa is not None and gp:
                        pa = float(pa) / float(gp)
                if ab and pa is not None:
                    out[str(ab).upper()] = {"points": float(pa)}
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(data)
    print(f"matchup: standings fallback teams={len(out)} ({sport})", flush=True)
    return out


def _fetch_team_defense(sport: str) -> Dict[str, Dict[str, float]]:
    """Return {team_abbrev: {stat_key: allowed_per_game}} for a sport."""
    # NBA/WNBA: nba_api ist die verlaessliche Opponent-Quelle; ESPN-statistics
    # liefert dort oft nur Liga-Leader statt Team-fuer-Team-Defense.
    if sport.upper() in ("NBA", "WNBA"):
        nba = _fetch_nba_defense_nbaapi(sport)
        if nba:
            return nba
        fb = _fetch_standings_points(sport)
        if fb:
            return fb
    if requests is None:
        return {}
    paths = ESPN_LEAGUE.get(sport.upper())
    stat_map = STAT_MATCH.get(sport.upper())
    if not paths or not stat_map:
        return {}
    sport_path, league = paths
    # ESPN core API: opponent (against) team stats, season averages.
    url = (f"https://site.api.espn.com/apis/site/v2/sports/{sport_path}/{league}/"
           f"statistics")
    try:
        r = requests.get(url, headers=_UA, timeout=_TIMEOUT)
        data = r.json() if r.ok else None
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    out: Dict[str, Dict[str, float]] = {}
    # ESPN nests team stat leaders under various shapes; walk defensively.
    teams = (data.get("teams") or data.get("stats") or [])
    for team in teams if isinstance(teams, list) else []:
        info = team.get("team") or {}
        ab = info.get("abbreviation") or info.get("shortDisplayName")
        if not ab:
            continue
        cats = team.get("statistics") or team.get("stats") or []
        bag: Dict[str, float] = {}
        for cat in cats if isinstance(cats, list) else []:
            nm = _norm(cat.get("name") or cat.get("displayName"))
            val = cat.get("value")
            if val is None:
                val = cat.get("perGameValue")
            for stat_key, frags in stat_map.items():
                if any(_norm(f) in nm for f in frags):
                    try:
                        bag[stat_key] = float(val)
                    except (TypeError, ValueError):
                        pass
        if bag:
            out[str(ab).upper()] = bag
    return out


def _ranked(sport: str) -> Dict[str, Dict[str, dict]]:
    """team -> stat -> {allowed, rank, over_friendliness(0..1)}."""
    key = sport.upper()
    if key in _cache:
        return _cache[key]
    defense = _fetch_team_defense(key)
    ranked: Dict[str, Dict[str, dict]] = {t: {} for t in defense}
    stat_keys = STAT_MATCH.get(key, {})
    for stat in stat_keys:
        vals = [(t, d[stat]) for t, d in defense.items() if stat in d]
        if len(vals) < 4:
            continue
        # Rank 1 = allows MOST (softest for an over).
        vals.sort(key=lambda x: -x[1])
        n = len(vals)
        for i, (t, v) in enumerate(vals):
            friendliness = 1.0 - (i / (n - 1)) if n > 1 else 0.5
            ranked[t][stat] = {"allowed": round(v, 2), "rank": i + 1,
                               "of": n, "over_friendliness": round(friendliness, 3)}
    _cache[key] = ranked
    return ranked


def matchup_rating(sport: str, opponent_abbrev: str, stat: str,
                   direction: str = "over") -> Optional[dict]:
    """Rating for a player's stat vs an opponent defense, or None.

    Returns {rank, of, allowed, favourability(0..1), label}. favourability is
    over_friendliness for an over, inverted for an under. label is a short JK-
    style phrase for the card ("erlaubt 2.-meiste Rebounds").
    """
    if not _ENABLED or not opponent_abbrev:
        return None
    try:
        ranked = _ranked(sport)
    except Exception:
        return None
    entry = (ranked.get(str(opponent_abbrev).upper()) or {}).get(stat)
    if not entry:
        return None
    fav = entry["over_friendliness"]
    if str(direction).lower() == "under":
        fav = round(1.0 - fav, 3)
    de = {"points": "Punkte", "rebounds": "Rebounds", "assists": "Assists",
          "threes": "Dreier", "shots_on_goal": "Schüsse", "goals": "Tore",
          "passing_yards": "Passing Yards", "rushing_yards": "Rushing Yards",
          "receiving_yards": "Receiving Yards", "hits": "Hits",
          "strikeouts": "Strikeouts", "runs": "Runs"}.get(stat, stat)
    rank = entry["rank"]
    label = f"erlaubt {rank}.-meiste {de}" if rank <= entry["of"] // 2 else \
            f"erlaubt {entry['of'] - rank + 1}.-wenigste {de}"
    return {"rank": rank, "of": entry["of"], "allowed": entry["allowed"],
            "favourability": fav, "label": label}


def combo_matchup_rating(sport: str, opponent_abbrev: str, stats, direction: str = "over") -> Optional[dict]:
    """Matchup fuer kombinierte Maerkte (Double/Triple-Double, PRA, P+R, P+A).

    Ein DD/TD haengt an mehreren Kategorien gleichzeitig. Wir mitteln die
    Favourability ueber die beteiligten Stats (points/rebounds/assists) und
    bauen ein Label aus den beiden staerksten Matchups — genau die Sengun-Logik
    ('erlaubt 2.-meiste Rebounds UND 7.-meiste Assists'). Gibt None, wenn fuer
    keine Teilkategorie ein Rating existiert.
    """
    if not _ENABLED or not opponent_abbrev:
        return None
    parts = []
    for st in stats:
        r = matchup_rating(sport, opponent_abbrev, st, direction)
        if r:
            parts.append((st, r))
    if not parts:
        return None
    fav = round(sum(r["favourability"] for _, r in parts) / len(parts), 3)
    # zwei staerkste (niedrigster Rank = offenste Defense) fuers Label
    parts.sort(key=lambda x: x[1]["rank"])
    top = parts[:2]
    label = " · ".join(r["label"] for _, r in top)
    return {"favourability": fav, "label": label,
            "components": {st: r["rank"] for st, r in parts}, "of": parts[0][1]["of"]}


# Welche Kategorien ein kombinierter Markt-Key braucht.
COMBO_STATS = {
    "double_double": ("points", "rebounds", "assists"),
    "triple_double": ("points", "rebounds", "assists"),
    "pra": ("points", "rebounds", "assists"),
    "pr": ("points", "rebounds"),
    "pa": ("points", "assists"),
    "ra": ("rebounds", "assists"),
}


if __name__ == "__main__":
    import sys, json
    sp = sys.argv[1] if len(sys.argv) > 1 else "NBA"
    print(json.dumps(_ranked(sp), indent=2)[:2000])
