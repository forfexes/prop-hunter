#!/usr/bin/env python3
"""PROP HUNTER 13.10 source catalog extension."""
from pathlib import Path as _Path
_core=_Path(__file__).with_name("prop_hunter_source_catalog_core_1392.py")
exec(compile(_core.read_text(encoding="utf-8"),str(_core),"exec"),globals(),globals())
_existing={x.key for x in SOURCES};_extra=[]
if "opticodds" not in _existing:_extra.append(SourceSpec("opticodds","OpticOdds","sportsbook_aggregator","trial_key_required",100,True,("MLB","NBA","WNBA","NFL","NHL","NCAAB","NCAAF"),("official_json","multi_book","player_props","alt_lines","results","cache"),"https://opticodds.com/","Trial/key-gated v3 source. Up to 5 fixtures and 5 sportsbooks per odds request; strong fit for multi-book no-vig consensus."))
if "parlayapi" not in _existing:_extra.append(SourceSpec("parlayapi","ParlayAPI","sportsbook_aggregator","free_key_required",99,True,("MLB","NBA","WNBA","NFL","NHL","NCAAB","NCAAF"),("official_json","paired_props","multi_book","cache"),"https://parlay-api.com/","Optional free-key source; paired over/under rows are valuable for no-vig consensus."))
if "1xbet" not in _existing:_extra.append(SourceSpec("1xbet","1xBet LineFeed","sportsbook","public_best_effort",71,False,("MLB","NBA","WNBA","NFL","NHL","NCAAB","NCAAF"),("public_json","event_markets","cache"),"https://1xbet.com/","Keyless best-effort fallback adapted from NETRATTLER; no login/browser/proxy bypass."))
SOURCES=SOURCES+tuple(_extra)
