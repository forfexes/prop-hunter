"""Attach verified event start times to PROP HUNTER display tickets.

Read-only enrichment from already collected official/source provider prop data;
never infer a date from another match, today's clock, team aliases or season
schedule. An ambiguous/missing/naive timestamp is *never* displayed.
"""
from __future__ import annotations

from datetime import datetime, timezone


def _get(obj,key,default=None):
    return obj.get(key,default) if isinstance(obj,dict) else getattr(obj,key,default)


def _identity(obj):
    sport=str(_get(obj,"sport") or _get(obj,"source_sport") or "").casefold().strip()
    # These are two explicit labels for the SAME league, not a guess from
    # unspecified "basketball" (which may be WNBA or EuroLeague).
    if sport not in ("nba","basketball_nba"):
        return None
    sport="nba"
    game=" ".join(str(_get(obj,"game") or "").casefold().split())
    player=" ".join(str(_get(obj,"player") or "").casefold().split())
    if not all((sport,game,player)) or game in ("verified ladder","unknown","n/a"):
        return None
    return sport,game,player


def _utc_time(value):
    if value is None or value == "":
        return None
    try:
        parsed=value if isinstance(value,datetime) else datetime.fromisoformat(
            str(value).strip().replace("Z","+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc).isoformat()
    except (ValueError,TypeError,OverflowError):
        return None


def enrich_verified_tipoffs(picks, props):
    """Set *only* unique, source-verified kickoff on exact same player/game.

    Also accepts leg-level times for a ladder if all specified leg games agree
    with its parent game; never merge multi-game Builder/Lottery tipoffs.
    Returns a count of newly verified ticket timestamps.
    """
    rows={}
    for prop in props:
        identity=_identity(prop)
        if identity:
            stamp=_utc_time(_get(prop,"commence_time"))
            if stamp:
                rows.setdefault(identity,set()).add(stamp)
    updated=0
    for pick in picks:
        if str(_get(pick,"type") or "").casefold() not in ("single","ladder"):
            continue
        if _utc_time(_get(pick,"commence_time")):
            continue
        key=_identity(pick)
        if not key:
            continue
        times=rows.get(key,set()).copy()
        details=list(_get(pick,"leg_details") or [])
        if details and str(_get(pick,"type") or "").lower()=="ladder":
            for detail in details:
                game=" ".join(str(_get(detail,"game") or "").casefold().split())
                raw_sport=str(_get(detail,"sport") or "").casefold().strip()
                sport="nba" if raw_sport in ("nba","basketball_nba") else raw_sport
                athlete=" ".join(str(_get(detail,"player") or "").casefold().split())
                if game and game!=key[1]:
                    times.clear()
                    break
                if sport and sport!=key[0]:
                    times.clear()
                    break
                if athlete and athlete!=key[2]:
                    times.clear()
                    break
                stamp=_utc_time(_get(detail,"commence_time"))
                if stamp:
                    times.add(stamp)
        if len(times)==1:
            stamp=next(iter(times))
            if isinstance(pick,dict):
                pick["commence_time"]=stamp
            else:
                setattr(pick,"commence_time",stamp)
            updated+=1
    return updated
