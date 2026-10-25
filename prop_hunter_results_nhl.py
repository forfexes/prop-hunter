#!/usr/bin/env python3
"""PROP HUNTER — NHL official pending-pick result/gamelog collector."""
from __future__ import annotations
import os
from datetime import datetime, timezone
from prop_hunter_shared_utils import select_pick_rows, upsert_rows, safe_json_write, log, warn, norm_name, http_json
from prop_hunter_identity_hub import identity_match

OUT='prop_hunter_results_nhl_raw.json'
SEARCH='https://search.d3.nhle.com/api/v1/search/player'
API='https://api-web.nhle.com/v1'

def season_id(now=None):
    now=now or datetime.now(timezone.utc); y=now.year if now.month>=7 else now.year-1
    return f'{y}{y+1}'

def pending_players():
    rows=select_pick_rows(limit=int(os.getenv('NHL_PICK_SCAN_LIMIT','5000')))
    out=[]; seen=set()
    for r in rows:
        if str(r.get('sport') or r.get('league') or '').upper()!='NHL': continue
        if str(r.get('status') or r.get('result') or 'pending').lower() not in ('','pending','open','none','null','unsettled'): continue
        n=str(r.get('player_name') or r.get('player') or '').strip(); k=norm_name(n)
        words=set(k.split())
        bad=bool(words & {'standings','team','october','november','december'}) or len(n.split())<2
        if n and k not in seen and not bad: seen.add(k); out.append(n)
    return out[:max(1,int(os.getenv('NHL_RESULTS_PLAYER_CAP','80')))]

def _candidate_name(row):
    if not isinstance(row,dict): return ''
    for key in ('name','fullName','playerName','displayName'):
        value=row.get(key)
        if isinstance(value,str) and value.strip(): return value.strip()
        if isinstance(value,dict):
            for k2 in ('default','en','value'):
                if isinstance(value.get(k2),str) and value.get(k2).strip(): return value.get(k2).strip()
    first=row.get('firstName'); last=row.get('lastName')
    def _txt(v):
        if isinstance(v,str): return v.strip()
        if isinstance(v,dict):
            for k in ('default','en','value'):
                if isinstance(v.get(k),str) and v.get(k).strip(): return v.get(k).strip()
        return ''
    full=f'{_txt(first)} {_txt(last)}'.strip()
    return full

def player_id(name):
    data=http_json(SEARCH,params={'q':name,'culture':'en-us','limit':8},retries=1) or []
    if isinstance(data,dict): data=data.get('searchResults') or data.get('playerSearchResults') or data.get('data') or []
    if not isinstance(data,list): return None
    exact=[]; fuzzy=[]
    for row in data:
        if not isinstance(row,dict) or not row.get('playerId'): continue
        cname=_candidate_name(row)
        if not cname: continue
        if norm_name(cname)==norm_name(name): exact.append(row)
        elif identity_match(name,cname,threshold=96): fuzzy.append(row)
    matches=exact or fuzzy
    if len(matches)>1:
        active=[r for r in matches if str(r.get('active') or '').lower() in ('true','1') or r.get('teamAbbrev') or r.get('currentTeamAbbrev')]
        if len(active)==1: matches=active
    if len(matches)!=1:
        if len(matches)>1: warn(f'NHL player search ambiguous: {name} matches={len(matches)}')
        elif data: warn(f'NHL player search no safe identity match: {name}')
        return None
    return matches[0].get('playerId')

def logs_for(name,last_n=30):
    pid=player_id(name)
    if not pid: return []
    data=http_json(f'{API}/player/{pid}/game-log/now',retries=1) or {}
    rows=[]; season=season_id()
    for g in (data.get('gameLog') or [])[:last_n]:
        goals=float(g.get('goals') or 0); assists=float(g.get('assists') or 0)
        rows.append({'sport':'NHL','league':'NHL','season':season,'source':'nhl_official_api',
          'source_game_id':str(g.get('gameId') or ''),'game_id':str(g.get('gameId') or ''),
          'game_date':str(g.get('gameDate') or '')[:10],'player_name':name,'normalized_name':norm_name(name),
          'team':g.get('teamAbbrev'),'opponent':g.get('opponentAbbrev'),
          'goals':goals,'assists_hockey':assists,'hockey_points':goals+assists,
          'shots_on_goal':float(g.get('shots') or 0),'goalie_saves':float(g.get('saves') or 0) if g.get('saves') is not None else None,
          'blocked_shots':float(g.get('blockedShots') or 0) if g.get('blockedShots') is not None else None,
          'power_play_points':float(g.get('powerPlayPoints') or 0),
          'toi':g.get('toi'),'raw':g})
    return [r for r in rows if r['game_id'] and r['game_date']]

def main():
    players=pending_players(); rows=[]
    for name in players:
        try: rows.extend(logs_for(name,int(os.getenv('LAST_N_GAMES','30'))))
        except Exception as e: warn(f'NHL gamelog failed {name}: {e}')
    safe_json_write(OUT,rows)
    if rows: upsert_rows('prop_hunter_player_gamelogs',rows,'sport,league,season,game_id,normalized_name')
    log(f'NHL results done: pending_players={len(players)} players={len(set(r["normalized_name"] for r in rows))} rows={len(rows)}')
if __name__=='__main__': main()
