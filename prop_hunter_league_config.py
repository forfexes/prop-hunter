#!/usr/bin/env python3
"""PROP HUNTER V13.5 — multisport league registry.
Only verified leagues are enabled for cards; prepared leagues can be activated without redesigning the pipeline.
"""
LEAGUES = {
 "BASEBALL":[
  {"league":"MLB","country":"USA","priority":1,"history":"mlb_statsapi","props_key":"baseball_mlb","status":"active"},
  {"league":"NPB","country":"Japan","priority":2,"history":"prepared_npb","props_key":"baseball_npb","status":"prepared"},
  {"league":"KBO","country":"Korea","priority":3,"history":"prepared_kbo","props_key":"baseball_kbo","status":"prepared"}],
 "BASKETBALL":[
  {"league":"NBA","country":"USA","priority":1,"history":"nba_api","props_key":"basketball_nba","status":"active"},
  {"league":"WNBA","country":"USA","priority":2,"history":"espn_wnba","props_key":"basketball_wnba","status":"active"},
  {"league":"NCAAB","country":"USA","priority":3,"history":"prepared_ncaab","props_key":"basketball_ncaab","status":"prepared"},
  {"league":"EUROLEAGUE","country":"Europe","priority":4,"history":"prepared_euroleague","props_key":"basketball_euroleague","status":"prepared"},
  {"league":"EUROCUP","country":"Europe","priority":5,"history":"prepared_eurocup","props_key":"basketball_eurocup","status":"prepared"},
  {"league":"ACB","country":"Spain","priority":6,"history":"prepared_acb","props_key":"basketball_spain_acb","status":"prepared"},
  {"league":"NBL","country":"Australia","priority":7,"history":"prepared_nbl","props_key":"basketball_nbl","status":"prepared"}],
 "AMERICAN_FOOTBALL":[
  {"league":"NFL","country":"USA","priority":1,"history":"nflverse","props_key":"americanfootball_nfl","status":"active"},
  {"league":"NCAAF","country":"USA","priority":2,"history":"cfbd","props_key":"americanfootball_ncaaf","status":"prepared"},
  {"league":"CFL","country":"Canada","priority":3,"history":"prepared_cfl","props_key":"americanfootball_cfl","status":"prepared"},
  {"league":"UFL","country":"USA","priority":4,"history":"prepared_ufl","props_key":"americanfootball_ufl","status":"prepared"},
  {"league":"ELF","country":"Europe","priority":5,"history":"prepared_elf","props_key":"americanfootball_elf","status":"prepared"}],
 "HOCKEY":[
  {"league":"NHL","country":"USA/Canada","priority":1,"history":"nhl_official_api","props_key":"icehockey_nhl","status":"active"},
  {"league":"SWISS_NL","country":"Switzerland","priority":2,"history":"prepared_swiss_nl","props_key":"icehockey_switzerland","status":"prepared"},
  {"league":"AHL","country":"USA/Canada","priority":3,"history":"prepared_ahl","props_key":"icehockey_ahl","status":"prepared"},
  {"league":"SHL","country":"Sweden","priority":4,"history":"prepared_shl","props_key":"icehockey_sweden","status":"prepared"},
  {"league":"LIIGA","country":"Finland","priority":5,"history":"prepared_liiga","props_key":"icehockey_finland","status":"prepared"},
  {"league":"DEL","country":"Germany","priority":6,"history":"prepared_del","props_key":"icehockey_germany","status":"prepared"},
  {"league":"KHL","country":"International","priority":7,"history":"prepared_khl","props_key":"icehockey_khl","status":"prepared"}],
}
def all_leagues(active_only=False):
 out=[]
 for sport,leagues in LEAGUES.items():
  for item in leagues:
   if active_only and item.get('status')!='active': continue
   x=dict(item); x['sport']=sport; out.append(x)
 return out
