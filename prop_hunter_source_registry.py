#!/usr/bin/env python3
"""PROP HUNTER V13.5 — league/source capability registry."""
from prop_hunter_league_config import LEAGUES
MARKETS={
 'BASEBALL':['HR','HITS','TOTAL_BASES','RBI','RUNS','STOLEN_BASES','PITCHER_K'],
 'BASKETBALL':['POINTS','REBOUNDS','ASSISTS','PRA','PA','PR','RA','3PM','STEALS','BLOCKS'],
 'AMERICAN_FOOTBALL':['ANYTIME_TD','RECEIVING','RUSHING','PASSING','RECEPTIONS'],
 'HOCKEY':['SHOTS_ON_GOAL','GOALS','POINTS','ASSISTS','GOALIE_SAVES','BLOCKED_SHOTS','POWER_PLAY_POINTS'],
}
SOURCE_REGISTRY={}
for family, leagues in LEAGUES.items():
 SOURCE_REGISTRY[family]={}
 for cfg in leagues:
  SOURCE_REGISTRY[family][cfg['league']]={
   'priority':cfg['priority'],'props_key':cfg['props_key'],'history_sources':[cfg['history']],
   'markets':MARKETS[family], 'status':cfg.get('status','prepared'), 'country':cfg.get('country')}
def iter_sources(active_only=False):
 for sport,leagues in SOURCE_REGISTRY.items():
  for league,cfg in leagues.items():
   if active_only and cfg.get('status')!='active': continue
   x=dict(cfg); x['sport']=sport; x['league']=league; yield x
def get_source(sport,league): return SOURCE_REGISTRY.get(str(sport).upper(),{}).get(str(league).upper())
