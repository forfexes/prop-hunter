"""Optional verified NBA position defense / usage evidence on live Prop objects.

Scraper cache is read-only and never substitutes odds, event identity or model
probabilities. Missing data => unchanged props, no Telegram disruption.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from prop_hunter_nba_context_engine import index_position_defense, matchup_position_evidence
from prop_hunter_nba_usage_features import attach_nba_usage_form, load_nba_usage_form


def attach_verified_nba_context(props, *, cache_path="output/nba_dvp_observed.json", sb_client=None, now=None):
    now=now or datetime.now(timezone.utc).date()
    dvp={}
    usage={}
    try:
        doc=json.loads(Path(cache_path).read_text(encoding="utf-8"))
        if doc.get("season") and isinstance(doc.get("rows"),list):
            dvp=index_position_defense(doc["rows"],as_of=now.isoformat())
    except (OSError,ValueError,TypeError,KeyError):
        pass
    if sb_client is not None:
        try:
            usage=load_nba_usage_form(sb_client)
        except Exception:
            usage={}
    attached=0
    for p in props or ():
        if str(getattr(p,"sport","")).upper()!="NBA":continue
        features=dict(getattr(p,"features",{}) or {})
        # No name matching: only canonical NBA IDs from an upstream observed feed.
        player_id=features.get("nba_player_id") or features.get("official_nba_player_id")
        if player_id is not None and usage:
            features=attach_nba_usage_form(features,player_id,usage)
        # Position and team must be explicit; never guess an NBA position.
        position=str(features.get("verified_position") or features.get("position") or "").upper().strip()
        own_team=str(features.get("player_team") or features.get("roster_team") or "").strip()
        if dvp and position and own_team:
            try:
                from prop_hunter_matchup import team_abbr
                own=team_abbr(own_team)
                home=team_abbr(getattr(p,"home",""))
                away=team_abbr(getattr(p,"away",""))
                opponent=away if own==home and home!=away else home if own==away and home!=away else None
                market=str(getattr(p,"market","") or "").lower()
                stat=("threes" if any(w in market for w in ("three","3pm","3pt","3-pt"))
                      else "rebounds" if "rebound" in market else "assists" if "assist" in market
                      else "points" if "point" in market else "")
                if opponent and stat:
                    evidence=matchup_position_evidence(dvp,opponent=opponent,position=position,stat=stat)
                    if evidence:
                        features["nba_dvp_position_evidence"]=evidence
                        attached+=1
            except Exception:
                pass
        p.features=features
    return props
