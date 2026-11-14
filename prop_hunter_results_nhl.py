#!/usr/bin/env python3
"""PROP HUNTER — NHL official pending-pick result/gamelog collector."""
from __future__ import annotations
import os
from datetime import datetime, timezone
from prop_hunter_shared_utils import select_settlement_picks as select_pick_rows, upsert_rows, safe_json_write, log, warn, norm_name, http_json
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

def goalie_saves(game):
    """Official goalie logs may expose shotsAgainst/goalsAgainst instead of saves."""
    def count(key):
        value = game.get(key)
        if value is None or isinstance(value, bool):
            return None
        try:
            n = float(value)
            return n if n >= 0 and n.is_integer() else None
        except (ValueError, TypeError):
            return None
    direct = count('saves')
    if direct is not None:
        return direct
    shots, goals = count('shotsAgainst'), count('goalsAgainst')
    return shots - goals if shots is not None and goals is not None and shots >= goals else None

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
          'shots_on_goal':float(g.get('shots') or 0),'goalie_saves':goalie_saves(g),
          'blocked_shots':float(g.get('blockedShots') or 0) if g.get('blockedShots') is not None else None,
          'power_play_points':float(g.get('powerPlayPoints') or 0),
          'toi':g.get('toi'),'raw':g})
    return [r for r in rows if r['game_id'] and r['game_date']]

def active_roster_players(day=None):
    """Aktive Skater der heutigen/naechsten NHL-Spiele ueber die offizielle API.

    Durchbricht den Teufelskreis: pending_players() liefert nur Spieler mit
    OFFENEN NHL-Picks. Ohne frische Gamelogs tippt der Bot aber keine NHL-Picks
    (nhl_l15_sample-Reject), also gibt es keine pending_players und nie neue
    Gamelogs. Hier holen wir die Roster der angesetzten Spiele, damit die
    L15-Historie da ist, BEVOR getippt wird. Rein additiv, fehlertolerant.
    """
    if os.getenv('NHL_ROSTER_PREFETCH','1').lower() not in ('1','true','yes','on'):
        return []
    day=day or datetime.now(timezone.utc).strftime('%Y-%m-%d')
    names=[]; seen=set(); teams=set()
    try:
        sched=http_json(f'{API}/schedule/{day}',retries=1) or {}
        for wk in sched.get('gameWeek',[]) or []:
            # nur heute + die naechsten 2 Tage, damit wir nicht die ganze Woche ziehen
            if str(wk.get('date') or '')[:10] > (datetime.now(timezone.utc)).strftime('%Y-%m-%d') and len(teams)>=12:
                continue
            for g in wk.get('games',[]) or []:
                for side in ('awayTeam','homeTeam'):
                    ab=(g.get(side) or {}).get('abbrev')
                    if ab: teams.add(ab)
    except Exception as e:
        warn(f'NHL schedule fetch failed: {e}')
        return []
    cap=int(os.getenv('NHL_ROSTER_PLAYER_CAP','180'))
    for ab in sorted(teams):
        try:
            roster=http_json(f'{API}/roster/{ab}/current',retries=1) or {}
            for grp in ('forwards','defensemen'):  # Goalies separat ueber Saves-Pfad
                for pl in roster.get(grp,[]) or []:
                    fn=(pl.get('firstName') or {}); ln=(pl.get('lastName') or {})
                    fn=fn.get('default') if isinstance(fn,dict) else fn
                    ln=ln.get('default') if isinstance(ln,dict) else ln
                    nm=f'{fn or ""} {ln or ""}'.strip()
                    k=norm_name(nm)
                    if nm and k not in seen and len(nm.split())>=2:
                        seen.add(k); names.append(nm)
        except Exception as e:
            warn(f'NHL roster {ab} failed: {e}')
        if len(names)>=cap: break
    return names[:cap]

def main():
    players=pending_players()
    pending_n=len(players)
    # Roster-Prefetch ergaenzt die pending-Spieler (ohne Duplikate), damit NHL-
    # Gamelogs auch dann vorhanden sind, wenn gerade keine NHL-Picks offen sind.
    seen={norm_name(n) for n in players}
    for nm in active_roster_players():
        if norm_name(nm) not in seen:
            seen.add(norm_name(nm)); players.append(nm)
    rows=[]
    for name in players:
        try: rows.extend(logs_for(name,int(os.getenv('LAST_N_GAMES','15'))))
        except Exception as e: warn(f'NHL gamelog failed {name}: {e}')
    safe_json_write(OUT,rows)
    if rows: upsert_rows('prop_hunter_player_gamelogs',rows,'sport,league,season,game_id,normalized_name')
    log(f'NHL results done: pending_players={pending_n} roster_added={len(players)-pending_n} players={len(set(r["normalized_name"] for r in rows))} rows={len(rows)}')
if __name__=='__main__': main()
