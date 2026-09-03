#!/usr/bin/env python3
"""PROP HUNTER — NHL official results/gamelogs for players in stored picks."""
from __future__ import annotations
import os
from datetime import datetime, timezone
from prop_hunter_shared_utils import select_pick_rows, upsert_rows, safe_json_write, log, warn, norm_name, http_json

OUT='prop_hunter_results_nhl_raw.json'
SEARCH='https://search.d3.nhle.com/api/v1/search'
API='https://api-web.nhle.com/v1'

def season_id(now=None):
    now=now or datetime.now(timezone.utc); y=now.year if now.month>=7 else now.year-1
    return f'{y}{y+1}'

def pending_players():
    rows=select_pick_rows(limit=int(os.getenv('NHL_PICK_SCAN_LIMIT','5000')))
    out=[]; seen=set()
    for r in rows:
        if str(r.get('sport') or r.get('league') or '').upper()!='NHL': continue
        if str(r.get('status') or r.get('result') or 'pending').lower() not in ('','pending','open','none'): continue
        n=str(r.get('player_name') or r.get('player') or '').strip(); k=norm_name(n)
        if n and k not in seen: seen.add(k); out.append(n)
    return out

def player_id(name):
    data=http_json(SEARCH,params={'q':name,'type':'player','culture':'en-us','limit':5},retries=1) or []
    if isinstance(data,dict): data=data.get('searchResults') or data.get('playerSearchResults') or []
    return (data[0].get('playerId') if data else None)

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
    return [r for r in rows if r['game_id']]

def main():
    rows=[]
    for name in pending_players():
        try: rows.extend(logs_for(name,int(os.getenv('LAST_N_GAMES','30'))))
        except Exception as e: warn(f'NHL gamelog failed {name}: {e}')
    safe_json_write(OUT,rows)
    if rows: upsert_rows('prop_hunter_player_gamelogs',rows,'sport,league,season,game_id,normalized_name')
    log(f'NHL results done: players={len(set(r["normalized_name"] for r in rows))} rows={len(rows)}')
if __name__=='__main__': main()
