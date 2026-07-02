#!/usr/bin/env python3
"""PROP HUNTER FINAL EDITION — universal backfill.
MLB StatsAPI, NBA nba_api, NFL nflreadpy. WNBA/International prepared safely.
"""
from __future__ import annotations
import os,re,json,time,hashlib
from pathlib import Path
from datetime import datetime
from typing import Any
import requests
try: from supabase import create_client
except Exception: create_client=None
CACHE_FILE=Path('prop_hunter_data_cache.json'); TIMEOUT=20
def log(x): print(datetime.now().strftime('%H:%M:%S'),'INFO   ',x,flush=True)
def warn(x): print(datetime.now().strftime('%H:%M:%S'),'WARNING',x,flush=True)
def norm_name(s:Any)->str:
    s=str(s or '').lower().strip(); s=re.sub(r"[^a-z0-9\s\.\-']",' ',s); return re.sub(r'\s+',' ',s).strip()
def to_num(x):
    try:
        if x is None or x=='': return None
        return float(x)
    except Exception: return None
def sb():
    if create_client is None: return None
    u=os.getenv('SUPABASE_URL','').strip(); k=os.getenv('SUPABASE_KEY','').strip()
    if not u or not k: return None
    try: return create_client(u,k)
    except Exception as e: warn(f'Supabase client failed: {e}'); return None
def upsert(table, rows, conflict=None):
    if not rows: return
    c=sb()
    if c is None: warn(f'Supabase missing; skipped {table} ({len(rows)} rows)'); return
    try:
        q=c.table(table).upsert(rows,on_conflict=conflict) if conflict else c.table(table).insert(rows)
        q.execute(); log(f'{table}: saved {len(rows)} rows')
    except Exception as e: warn(f'{table} save failed: {e}')
def http_json(url, params=None):
    try:
        r=requests.get(url,params=params or {},timeout=TIMEOUT,headers={'User-Agent':'PropHunterFinal/10'})
        if r.status_code>=400: warn(f'HTTP {r.status_code}: {url}'); return None
        return r.json()
    except Exception as e: warn(f'HTTP failed {url}: {e}'); return None
def load_cache():
    if not CACHE_FILE.exists(): return {}
    try: return json.loads(CACHE_FILE.read_text(encoding='utf-8'))
    except Exception: return {}
def players_from_cache(cache):
    players={'MLB':set(),'NBA':set(),'WNBA':set(),'NFL':set()}
    mlb=cache.get('mlb',{}) if isinstance(cache,dict) else {}
    for sec in ('batters_basic','pitchers_basic'):
        m=mlb.get(sec,{}) or {}
        if isinstance(m,dict):
            for n in m.keys():
                if n: players['MLB'].add(str(n))
    p=Path('prop_hunter_latest_props.json')
    if p.exists():
        try:
            data=json.loads(p.read_text(encoding='utf-8'))
            for it in data if isinstance(data,list) else []:
                sport=str(it.get('source_sport') or it.get('sport') or '').upper(); name=it.get('player') or it.get('player_name')
                if not name: continue
                if 'MLB' in sport or sport=='BASEBALL': players['MLB'].add(str(name))
                elif 'WNBA' in sport: players['WNBA'].add(str(name))
                elif 'NBA' in sport: players['NBA'].add(str(name))
                elif 'NFL' in sport: players['NFL'].add(str(name))
        except Exception: pass
    return players
def innings_to_float(x):
    try:
        s=str(x)
        if '.' not in s: return float(s)
        a,b=s.split('.',1); return float(a)+float(b)/3.0
    except Exception: return None
def mlb_search_player(name):
    data=http_json('https://statsapi.mlb.com/api/v1/people/search', {'names':name}); people=(data or {}).get('people') or []
    if not people: return None
    nn=norm_name(name)
    for p in people:
        if norm_name(p.get('fullName'))==nn: return p
    return people[0]
def mlb_gamelog(pid, group, season):
    data=http_json(f'https://statsapi.mlb.com/api/v1/people/{pid}/stats', {'stats':'gameLog','group':group,'season':season,'hydrate':'team'})
    stats=(data or {}).get('stats') or []
    return (stats[0].get('splits') or []) if stats else []
def parse_mlb_split(name, sp, season, pitching=False):
    st,tm,op,gm=sp.get('stat') or {},sp.get('team') or {},sp.get('opponent') or {},sp.get('game') or {}
    gid=str(gm.get('gamePk') or hashlib.md5(json.dumps(sp,sort_keys=True).encode()).hexdigest()[:16])
    row={'sport':'BASEBALL','league':'MLB','country':'USA','season':season,'source':'mlb_statsapi','source_game_id':gid,'game_id':gid,'game_date':sp.get('date'),'player_name':name,'normalized_name':norm_name(name),'team':tm.get('abbreviation') or tm.get('name'),'opponent':op.get('abbreviation') or op.get('name'),'home_away':str(sp.get('isHome')),'raw':sp}
    if pitching: row.update({'pitcher_strikeouts':to_num(st.get('strikeOuts')),'pitcher_innings':innings_to_float(st.get('inningsPitched')),'pitcher_hits_allowed':to_num(st.get('hits')),'pitcher_earned_runs':to_num(st.get('earnedRuns')),'pitcher_walks':to_num(st.get('baseOnBalls')),'pitcher_home_runs_allowed':to_num(st.get('homeRuns'))})
    else: row.update({'hits':to_num(st.get('hits')),'total_bases':to_num(st.get('totalBases')),'home_runs':to_num(st.get('homeRuns')),'rbi':to_num(st.get('rbi')),'runs':to_num(st.get('runs')),'strikeouts_batter':to_num(st.get('strikeOuts')),'walks_batter':to_num(st.get('baseOnBalls')),'stolen_bases':to_num(st.get('stolenBases'))})
    return row
def backfill_mlb(names,seasons=None,last_n=60):
    seasons=seasons or [str(datetime.now().year)]; rows=[]; cap=int(os.getenv('BACKFILL_PLAYER_CAP','150'))
    for i,nm in enumerate(sorted(names)):
        if i>=cap: warn(f'MLB runtime cap reached: {cap}'); break
        person=mlb_search_player(nm)
        if not person: continue
        full=person.get('fullName') or nm; pos=((person.get('primaryPosition') or {}).get('abbreviation')); group='pitching' if pos in ('P','SP','RP') else 'hitting'
        for season in seasons:
            splits=sorted(mlb_gamelog(person.get('id'),group,season),key=lambda x:x.get('date') or '',reverse=True)[:last_n]
            for sp in splits: rows.append(parse_mlb_split(full,sp,season,pitching=(group=='pitching')))
            time.sleep(0.05)
    upsert('prop_hunter_player_gamelogs',rows,'sport,league,season,game_id,normalized_name'); log(f'MLB backfill done: players={len(names)} rows={len(rows)}')
def backfill_nba_via_nba_api(names=None,seasons=None,last_n=82):
    import time as _time
    start = _time.time()
    max_runtime = int(os.getenv('NBA_BACKFILL_MAX_SECONDS','120'))
    try:
        from nba_api.stats.static import players as nba_players
        from nba_api.stats.endpoints import playergamelog
    except Exception as e: warn(f'nba_api unavailable: {e}'); return
    seasons=seasons or [os.getenv('NBA_SEASON','2025-26')]
    wanted={norm_name(x) for x in (names or [])}
    if not wanted:
        warn('NBA backfill: keine Spielernamen im Cache, skip (verhindert All-Time-Roster-Loop)')
        return
    allp=nba_players.get_players(); rows=[]; cap=int(os.getenv('BACKFILL_PLAYER_CAP','15'))
    selected=[p for p in allp if norm_name(p.get('full_name')) in wanted]
    if not selected and wanted: selected=[p for p in allp if any(w in norm_name(p.get('full_name')) or norm_name(p.get('full_name')) in w for w in wanted)]
    for p in selected[:cap]:
        if _time.time() - start > max_runtime:
            warn(f'NBA backfill: Zeitlimit {max_runtime}s erreicht, stoppe'); break
        full=p.get('full_name'); pid=p.get('id')
        for season in seasons:
            if _time.time() - start > max_runtime: break
            try: df=playergamelog.PlayerGameLog(player_id=pid,season=season,season_type_all_star='Regular Season',timeout=8).get_data_frames()[0]
            except Exception as e: warn(f'nba gamelog failed {full} {season}: {e}'); continue
            for _,r in df.head(last_n).iterrows():
                pts=to_num(r.get('PTS')); reb=to_num(r.get('REB')); ast=to_num(r.get('AST'))
                rows.append({'sport':'BASKETBALL','league':'NBA','country':'USA','season':season,'source':'nba_api','source_game_id':str(r.get('Game_ID') or r.get('GAME_ID')),'game_id':str(r.get('Game_ID') or r.get('GAME_ID')),'game_date':str(r.get('GAME_DATE'))[:10] if r.get('GAME_DATE') is not None else None,'player_name':full,'normalized_name':norm_name(full),'opponent':str(r.get('MATCHUP') or ''),'minutes':to_num(r.get('MIN')),'points':pts,'rebounds':reb,'assists':ast,'pra':(pts or 0)+(reb or 0)+(ast or 0),'ra':(reb or 0)+(ast or 0),'threes_made':to_num(r.get('FG3M')),'steals':to_num(r.get('STL')),'blocks':to_num(r.get('BLK')),'turnovers':to_num(r.get('TOV')),'double_double':sum(1 for v in (pts,reb,ast) if (v or 0)>=10)>=2,'triple_double':sum(1 for v in (pts,reb,ast) if (v or 0)>=10)>=3,'raw':dict(r)})
            time.sleep(0.35)
    upsert('prop_hunter_player_gamelogs',rows,'sport,league,season,game_id,normalized_name'); log(f'NBA backfill done: players={len(selected)} rows={len(rows)}')
def backfill_nfl_via_nflreadpy(seasons=None):
    seasons=seasons or [int(os.getenv('NFL_SEASON',str(datetime.now().year)))]
    try: import nflreadpy as nfl
    except Exception as e: warn(f'nflreadpy unavailable: {e}'); return
    try:
        data=nfl.load_player_stats(seasons=seasons); pdf=data.to_pandas() if hasattr(data,'to_pandas') else data
    except Exception as e: warn(f'nflreadpy load_player_stats failed: {e}'); return
    rows=[]; cap=int(os.getenv('BACKFILL_ROW_CAP','5000'))
    for _,r in pdf.head(cap).iterrows():
        name=r.get('player_display_name') or r.get('player_name') or r.get('name')
        if not name: continue
        week=r.get('week'); season=str(r.get('season') or seasons[0]); gid=str(r.get('recent_team') or '')+'_'+season+'_'+str(week)+'_'+norm_name(name)
        rows.append({'sport':'AMERICAN_FOOTBALL','league':'NFL','country':'USA','season':season,'source':'nflreadpy','source_game_id':gid,'game_id':gid,'player_name':name,'normalized_name':norm_name(name),'team':r.get('recent_team'),'opponent':r.get('opponent_team'),'receptions':to_num(r.get('receptions')),'receiving_yards':to_num(r.get('receiving_yards')),'rushing_yards':to_num(r.get('rushing_yards')),'rush_attempts':to_num(r.get('carries')),'passing_yards':to_num(r.get('passing_yards')),'passing_tds':to_num(r.get('passing_tds')),'interceptions':to_num(r.get('interceptions')),'touchdowns':to_num(r.get('rushing_tds') or 0)+to_num(r.get('receiving_tds') or 0),'targets':to_num(r.get('targets')),'raw':dict(r)})
    upsert('prop_hunter_player_gamelogs',rows,'sport,league,season,game_id,normalized_name'); log(f'NFL backfill done: rows={len(rows)}')
def main():
    log('='*44); log('PROP HUNTER FINAL EDITION UNIVERSAL BACKFILL'); log('='*44)
    players=players_from_cache(load_cache()); log('players from cache: '+', '.join(f'{k}={len(v)}' for k,v in players.items()))
    last_n=int(os.getenv('LAST_N_GAMES','60'))
    if os.getenv('BACKFILL_MLB','1')=='1': backfill_mlb(players['MLB'], os.getenv('MLB_BACKFILL_SEASONS',str(datetime.now().year)).split(','), last_n)
    if os.getenv('BACKFILL_NBA','1')=='1': backfill_nba_via_nba_api(players['NBA'], os.getenv('NBA_BACKFILL_SEASONS',os.getenv('NBA_SEASON','2025-26')).split(','), last_n)
    if os.getenv('BACKFILL_WNBA','1')=='1': log('WNBA backfill prepared: ESPN/wehoop adapter next')
    if os.getenv('BACKFILL_NFL','1')=='1': backfill_nfl_via_nflreadpy([int(x) for x in os.getenv('NFL_BACKFILL_SEASONS',str(datetime.now().year)).split(',') if x.strip().isdigit()])
    log('universal backfill done')
if __name__=='__main__': main()
