#!/usr/bin/env python3
"""PROP HUNTER FINAL EDITION — source registry."""
SOURCE_REGISTRY={
 'BASEBALL':{
  'MLB':{'priority':1,'props_key':'baseball_mlb','history_sources':['mlb_statsapi','pybaseball'],'markets':['HR','HITS','TOTAL_BASES','PITCHER_K'],'status':'active'},
  'KBO':{'priority':2,'props_key':'baseball_kbo','history_sources':['future_kbo'],'markets':['HR','HITS','TOTAL_BASES','PITCHER_K'],'status':'prepared'},
  'NPB':{'priority':3,'props_key':'baseball_npb','history_sources':['future_npb'],'markets':['HR','HITS','TOTAL_BASES','PITCHER_K'],'status':'prepared'},
  'CPBL':{'priority':4,'props_key':'baseball_cpbl','history_sources':['future_cpbl'],'markets':['HR','HITS','TOTAL_BASES'],'status':'prepared'}},
 'BASKETBALL':{
  'NBA':{'priority':1,'props_key':'basketball_nba','history_sources':['nba_api','espn'],'markets':['PRA','RBA','ASSISTS','REBOUNDS','POINTS','DOUBLE_DOUBLE','TRIPLE_DOUBLE'],'status':'active'},
  'WNBA':{'priority':2,'props_key':'basketball_wnba','history_sources':['espn','wehoop_data'],'markets':['PRA','RBA','ASSISTS','REBOUNDS','POINTS','DOUBLE_DOUBLE'],'status':'active'},
  'EUROLEAGUE':{'priority':3,'props_key':'basketball_euroleague','history_sources':['future_euroleague_api','hackastat'],'markets':['PRA','RBA','ASSISTS','REBOUNDS','POINTS'],'status':'prepared'},
  'ACB':{'priority':4,'props_key':'basketball_spain_acb','history_sources':['future_acb'],'markets':['PRA','RBA'],'status':'prepared'},
  'NBL':{'priority':5,'props_key':'basketball_nbl','history_sources':['future_nbl'],'markets':['PRA','RBA'],'status':'prepared'}},
 'AMERICAN_FOOTBALL':{
  'NFL':{'priority':1,'props_key':'americanfootball_nfl','history_sources':['nflreadpy','nflverse_data','espn'],'markets':['ANYTIME_TD','FIRST_TD','2PLUS_TD','RECEIVING','RUSHING','PASSING','QB_RUSH'],'status':'active'},
  'NCAAF':{'priority':2,'props_key':'americanfootball_ncaaf','history_sources':['future_cfbd'],'markets':['ANYTIME_TD','RECEIVING','RUSHING','PASSING'],'status':'prepared'},
  'CFL':{'priority':3,'props_key':'americanfootball_cfl','history_sources':['future_cfl'],'markets':['ANYTIME_TD','RECEIVING','RUSHING','PASSING'],'status':'prepared'},
  'ELF':{'priority':4,'props_key':'americanfootball_elf','history_sources':['future_elf'],'markets':['ANYTIME_TD','RECEIVING','RUSHING','PASSING'],'status':'prepared'}}}
def iter_sources(active_only=False):
    for sport,leagues in SOURCE_REGISTRY.items():
        for league,cfg in leagues.items():
            if active_only and cfg.get('status')!='active': continue
            x=dict(cfg); x['sport']=sport; x['league']=league; yield x
def get_source(sport, league): return SOURCE_REGISTRY.get(str(sport).upper(),{}).get(str(league).upper())
