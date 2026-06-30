#!/usr/bin/env python3
from __future__ import annotations
import hashlib, importlib.util, json, os, re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
import requests

SUPABASE_URL=os.environ.get('SUPABASE_URL','').rstrip('/')
SUPABASE_KEY=os.environ.get('SUPABASE_KEY','').strip()
TODAY=date.today().isoformat()
MIN_EDGE=float(os.environ.get('PH_MIN_EDGE','3.0'))
SPORT_ALLOW={'baseball_mlb','mlb','basketball_wnba','wnba','basketball_nba','nba','americanfootball_nfl','nfl'}
MARKET_HINTS=('points','rebounds','assists','pra','threes','3pm','three','strikeouts','total bases','hits','home run','homer','rbis','walks','steals','blocks','turnovers','rebounds_assists','points_rebounds','points_assists','points_rebounds_assists')

def log(m): print(f"{datetime.now(timezone.utc).strftime('%H:%M:%S')} INFO    {m}", flush=True)
def warn(m): print(f"{datetime.now(timezone.utc).strftime('%H:%M:%S')} WARNING {m}", flush=True)
def hdr(): return {'apikey':SUPABASE_KEY,'Authorization':f'Bearer {SUPABASE_KEY}','Content-Type':'application/json','Prefer':'resolution=merge-duplicates'}
def norm(x): return str(x or '').strip()
def get_any(r:Dict[str,Any], keys:Iterable[str], default=None):
    for k in keys:
        if k in r and r[k] not in (None,''): return r[k]
    return default
def fnum(x):
    try:
        if x is None or x=='': return None
        return float(x)
    except Exception: return None
def dec_odds(x):
    v=fnum(x)
    if v is None: return None
    if abs(v)>20:
        return round(1+v/100,4) if v>0 else round(1+100/abs(v),4)
    return v
def implied(o): return 100.0/o if o and o>1 else 0.0

def clean_market(m):
    s=norm(m); low=s.lower().replace('_',' ')
    if 'points rebounds assists' in low: return 'PRA'
    if 'points rebounds' in low: return 'PR'
    if 'points assists' in low: return 'PA'
    if 'rebounds assists' in low: return 'Reb+Ast'
    if 'three' in low or '3pm' in low or 'threes' in low: return '3PM'
    if 'home run' in low or 'homer' in low: return 'Home Run'
    if 'strikeout' in low: return 'Strikeouts'
    if 'total base' in low: return 'Total Bases'
    if 'point' in low: return 'Points'
    if 'rebound' in low: return 'Rebounds'
    if 'assist' in low: return 'Assists'
    if 'steal' in low: return 'Steals'
    if 'block' in low: return 'Blocks'
    if 'turnover' in low: return 'Turnovers'
    if 'hit' in low: return 'Hits'
    if 'walk' in low: return 'Walks'
    return s.replace('_',' ').title()

def sport_ok(sport, market):
    blob=f'{sport} {market}'.lower()
    if any(x in blob for x in ['soccer','football_epl','fussball']): return False
    if sport.lower() in SPORT_ALLOW: return True
    return any(h in blob for h in MARKET_HINTS)

def side_from(r):
    s=norm(get_any(r,['side','outcome','label','selection','name'],'Over')).lower()
    if 'under' in s: return 'Under'
    if 'over' in s: return 'Over'
    return s.title() if s else 'Over'

def dedup(row):
    raw='|'.join([norm(row.get(k)).lower() for k in ['date','sport','event_id','player','market','line','side','book']])
    return hashlib.sha1(raw.encode()).hexdigest()

def normalize_row(r):
    player=norm(get_any(r,['player','player_name','athlete','participant','description','name']))
    market=clean_market(get_any(r,['market','market_name','market_key','prop','stat','category','type'],''))
    sport=norm(get_any(r,['sport','sport_key','league','sport_name'],''))
    if not player or not market or not sport_ok(sport, market): return None
    odds=dec_odds(get_any(r,['odds','price','decimal_odds','best_odds','book_odds','odd']))
    if odds is None or odds<=1.01: return None
    line=fnum(get_any(r,['line','point','points','handicap','threshold','total']))
    prob=fnum(get_any(r,['prob','probability','model_prob','fair_prob','hit_prob']))
    edge=fnum(get_any(r,['edge','edge_pct','value_edge','ev','ev_pct']))
    if prob is not None and prob<=1: prob*=100
    if edge is not None and abs(edge)<=1: edge*=100
    if prob is None: prob=round(implied(odds)+4,2)
    if edge is None: edge=round(prob-implied(odds),2)
    if edge<MIN_EDGE: return None
    out={'date':norm(get_any(r,['date','commence_date'],TODAY))[:10] or TODAY,'sport':sport or 'unknown','league':norm(get_any(r,['league','sport_title','competition'],sport)),'event_id':norm(get_any(r,['event_id','game_id','match_id','id'],'')),'game':norm(get_any(r,['game','event','matchup'],'')),'home_team':norm(get_any(r,['home_team'],'')),'away_team':norm(get_any(r,['away_team'],'')),'team':norm(get_any(r,['team','player_team','team_name'],'')),'player':player,'market':market,'line':line,'side':side_from(r),'odds':odds,'book':norm(get_any(r,['book','bookmaker','sportsbook'],'')),'source':norm(get_any(r,['source'],'normalizer_v7')),'prob':prob,'fair_odds':round(100/prob,4) if prob else None,'edge':edge,'confidence':fnum(get_any(r,['confidence','conf'],None)),'stake':fnum(get_any(r,['stake'],None)),'projection':fnum(get_any(r,['projection','proj'],None)),'season_avg':fnum(get_any(r,['season_avg','avg'],None)),'l5_avg':fnum(get_any(r,['l5_avg','last5_avg'],None)),'l10_avg':fnum(get_any(r,['l10_avg','last10_avg'],None)),'hit_l5':get_any(r,['hit_l5','l5_hit'],None),'hit_l10':get_any(r,['hit_l10','l10_hit'],None),'minutes_proj':fnum(get_any(r,['minutes_proj','min_proj'],None)),'opponent':norm(get_any(r,['opponent'],'')),'matchup_note':norm(get_any(r,['matchup_note','note','why'],'')),'raw':r}
    out['dedup_key']=dedup(out)
    return out

def flatten(obj):
    rows=[]
    if isinstance(obj,list):
        for x in obj: rows+=flatten(x)
    elif isinstance(obj,dict):
        for k in ['props','markets','outcomes','data','items','rows','picks']:
            if isinstance(obj.get(k),list):
                base={kk:vv for kk,vv in obj.items() if kk not in [k,'data','items']}
                for x in obj[k]:
                    rows+=flatten({**base, **x} if isinstance(x,dict) else x)
                return rows
        rows.append(obj)
    return rows

def load_json():
    rows=[]
    for p in [Path('prop_hunter_event_props.json'),Path('event_props.json'),Path('props.json'),Path('prop_hunter_data_cache.json')]:
        if p.exists():
            try:
                got=flatten(json.loads(p.read_text(encoding='utf-8'))); log(f'json {p}: {len(got)} candidate rows'); rows+=got
            except Exception as e: warn(f'json {p} failed: {e}')
    return rows

def load_module():
    path=Path('prop_hunter_event_props.py')
    if not path.exists(): return []
    try:
        spec=importlib.util.spec_from_file_location('prop_hunter_event_props',str(path)); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        for name in ['fetch_event_props','load_event_props','main_collect','collect_props']:
            fn=getattr(mod,name,None)
            if callable(fn):
                try:
                    got=flatten(fn()); log(f'module {name}: {len(got)} candidate rows'); return got
                except TypeError: pass
                except Exception as e: warn(f'module {name} failed: {e}')
    except Exception as e: warn(f'import prop_hunter_event_props.py failed: {e}')
    return []

def upsert(rows):
    if not SUPABASE_URL or not SUPABASE_KEY: warn('Supabase env missing'); return
    if not rows: warn('no normalized rows to upsert'); return
    url=f'{SUPABASE_URL}/rest/v1/prop_hunter_normalized'
    total=0
    for i in range(0,len(rows),200):
        chunk=rows[i:i+200]
        r=requests.post(url,headers=hdr(),params={'on_conflict':'dedup_key'},json=chunk,timeout=40)
        if r.status_code>=300: warn(f'upsert failed {r.status_code}: {r.text[:500]}')
        else: total+=len(chunk)
    log(f'upserted normalized rows: {total}/{len(rows)}')

def main():
    log('PROP HUNTER NORMALIZER V7')
    candidates=load_module()+load_json()
    out=[]; seen=set()
    for r in candidates:
        nr=normalize_row(r)
        if nr and nr['dedup_key'] not in seen:
            seen.add(nr['dedup_key']); out.append(nr)
    log(f'normalized candidates: {len(candidates)} -> {len(out)}')
    upsert(out); return 0
if __name__=='__main__': raise SystemExit(main())
