#!/usr/bin/env python3
"""PROP HUNTER 13.10.1 source catalog extension."""
from pathlib import Path as _Path
_core=_Path(__file__).with_name('prop_hunter_source_catalog_core_1392.py')
exec(compile(_core.read_text(encoding='utf-8'),str(_core),'exec'),globals(),globals())
_existing={x.key for x in SOURCES};_extra=[]
def add(spec):
    if spec.key not in _existing:_extra.append(spec);_existing.add(spec.key)
add(SourceSpec('draftkings_direct','DraftKings Direct','sportsbook','public_best_effort',96,True,('MLB','NBA','NFL','NHL'),('public_json','player_props','alt_lines','cache'),'https://sportsbook.draftkings.com/','Keyless direct sportsbook JSON; real O/U and observed X+ ladder prices only.'))
add(SourceSpec('fanduel_direct','FanDuel Direct','sportsbook','public_best_effort',95,True,('MLB','NBA','WNBA','NFL','NHL'),('public_json','player_props','thresholds','cache'),'https://sportsbook.fanduel.com/','Keyless event-page player selections; observed threshold props only.'))
add(SourceSpec('bovada_direct','Bovada Direct','sportsbook','public_best_effort',94,True,('MLB','NBA','WNBA','NFL','NHL','NCAAB','NCAAF'),('public_json','player_props','paired_props','cache'),'https://www.bovada.lv/sports','Keyless coupon API; strong O/U pair candidate where public feed exposes props.'))
add(SourceSpec('betrivers_direct','BetRivers Direct','sportsbook','public_best_effort',93,True,('MLB','NBA','WNBA','NFL','NHL','NCAAB','NCAAF'),('kambi_public_json','player_props','paired_props','cache'),'https://www.betrivers.com/','Keyless Kambi operator feed, audited as its own bookmaker.'))
add(SourceSpec('opticodds','OpticOdds','sportsbook_aggregator','trial_key_required',100,True,('MLB','NBA','WNBA','NFL','NHL','NCAAB','NCAAF'),('official_json','multi_book','player_props','alt_lines','results','cache'),'https://opticodds.com/','Trial/key-gated v3 source; strong multi-book consensus fallback.'))
add(SourceSpec('parlayapi','ParlayAPI','sportsbook_aggregator','free_key_required',89,True,('MLB','NBA','WNBA','NFL','NHL','NCAAB','NCAAF'),('official_json','paired_props','multi_book','cache'),'https://parlay-api.com/','Optional keyed paired-prop fallback.'))
add(SourceSpec('1xbet','1xBet LineFeed','sportsbook','public_best_effort',71,False,('MLB','NBA','WNBA','NFL','NHL','NCAAB','NCAAF'),('public_json','event_markets','cache'),'https://1xbet.com/','Keyless best-effort fallback adapted from NETRATTLER; no login/browser/proxy bypass.'))
SOURCES=SOURCES+tuple(_extra)
