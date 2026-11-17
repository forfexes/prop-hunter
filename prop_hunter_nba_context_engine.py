"""NBA context profiles from *observed* shot events and position-defense rows.

This module never fetches from the network and never manufactures observations.
The pre-tip aggregation excludes any match lacking canonical identity or dates.
All output is auxiliary evidence; no model probability changes without validation.
"""
from collections import Counter, defaultdict
from datetime import date
from math import isfinite
from prop_hunter_nba_context_sources import observed_dvp, POSITIONS, DVP_STATS

VALID_SHOT_ZONES = frozenset({
    "restricted area", "in the paint (non-ra)", "mid-range",
    "left corner 3", "right corner 3", "above the break 3", "backcourt",
})
ALLOWED_SHOT_SOURCES = frozenset({"nba_official_shotchart", "verified_pbp_event"})


def _date(raw):
    raw = str(raw or "").strip().replace("-", "")
    if len(raw) != 8 or not raw.isdecimal():
        return None
    try:
        return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
    except ValueError:
        return None


def shot_observation(row, *, nba_player_id, season, before_date):
    """Single verified shot from NBA ShotChartDetail-shaped observations."""
    if not isinstance(row, dict) or row.get("source") not in ALLOWED_SHOT_SOURCES:
        return None
    try:
        player_id = int(row.get("player_id"))
        if player_id != int(nba_player_id) or player_id <= 0:
            return None
        game = str(row["game_id"])
        if not (game.isdecimal() and len(game) == 10):
            return None
        d = _date(row.get("game_date"))
        cutoff = date.fromisoformat(str(before_date))
        season_start = int(str(season)[:4])
        if not d or not date(season_start, 10, 1) <= d < cutoff:
            return None
        attempted = int(row["shot_attempted_flag"])
        made = int(row["shot_made_flag"])
        if attempted != 1 or made not in (0, 1):
            return None
        zone = str(row["shot_zone_basic"]).strip().lower()
        if zone not in VALID_SHOT_ZONES:
            return None
        event_id = int(row["game_event_id"])
        if event_id < 0:
            return None
    except (TypeError, ValueError, KeyError, OverflowError):
        return None
    return (game, event_id, d.isoformat(), zone, made)


def shot_form(events, *, nba_player_id, season, before_date):
    """Player zones for up to 5/10/15 distinct dated games, zero leakage."""
    seen = set()
    valid = []
    for row in events or ():
        shot = shot_observation(row, nba_player_id=nba_player_id,
                                season=season, before_date=before_date)
        if shot is not None and shot[:2] not in seen:
            seen.add(shot[:2])
            valid.append(shot)
    days = {}
    for shot in valid:
        days.setdefault((shot[2], shot[0]), []).append(shot)
    games = sorted(days, reverse=True)
    output = {"player_id": int(nba_player_id), "source": "nba_official_shotchart",
              "observed_games": len(games), "model_ready": False}
    for n in (5, 10, 15):
        selected = games[:n]
        zone_counts = defaultdict(lambda: [0, 0])
        for game in selected:
            for shot in days[game]:
                zone_counts[shot[3]][0] += 1
                zone_counts[shot[3]][1] += shot[4]
        output["l" + str(n)] = {
            "games": len(selected),
            "zones": {z: {"fga": count[0], "fgm": count[1],
                           "fg_pct": round(count[1] / count[0], 4)}
                      for z, count in zone_counts.items() if count[0]},
        }
    return output


def index_position_defense(rows, *, as_of):
    """Only dated, verified raw allowed PTS/REB/AST/3PM values by position."""
    grouped = defaultdict(list)
    for row in rows or ():
        parsed = observed_dvp(row, as_of=as_of)
        if parsed:
            grouped[(parsed["opponent_team"], parsed["position"], parsed["stat"])].append(parsed)
    # Ambiguous duplicate values/sources cannot be silently merged.
    return {key: batch[0] for key, batch in grouped.items()
            if len(batch) == 1}


def matchup_position_evidence(index, *, opponent, position, stat):
    """Position assignment must come from a verified upstream player mapping."""
    team = str(opponent or "").upper()
    position = str(position or "").upper()
    stat = str(stat or "").lower()
    if len(team) != 3 or position not in POSITIONS or stat not in DVP_STATS:
        return None
    item = index.get((team, position, stat))
    if item is None:
        return None
    return dict(item, evidence_only=True, model_ready=False)
