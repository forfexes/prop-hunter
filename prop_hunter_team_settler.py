#!/usr/bin/env python3
"""Settle explicit team/game totals from exact final ESPN event scoreboards."""
import re
from datetime import datetime, timedelta, timezone
from prop_hunter_shared_utils import select_settlement_picks, http_json, pick_id, hash_key, norm_name, now_iso, supabase_client, log
from prop_hunter_settler import detect_stat, line_of_pick, side_of_pick, result_for_value, persist_settlements

PATHS={'NCAAF':'football/college-football','NFL':'football/nfl','NBA':'basketball/nba','WNBA':'basketball/wnba','NHL':'hockey/nhl','MLB':'baseball/mlb'}
STATS={'NCAAF':'points','NFL':'points','NBA':'points','WNBA':'points','NHL':'goals','MLB':'runs'}

def norm(value):
    return re.sub(r'[^a-z0-9]+',' ',str(value or '').lower()).strip()

def context(pick):
    raw=pick.get('raw') if isinstance(pick.get('raw'),dict) else {}
    game=pick.get('game') or raw.get('game') or ''
    start=pick.get('commence_time') or raw.get('commence_time')
    try:
        dt=datetime.fromisoformat(str(start).replace('Z','+00:00'))
        if dt.tzinfo is None:return None
        dt=dt.astimezone(timezone.utc)
    except (ValueError,TypeError):return None
    if not re.search(r'@|\bvs\.?\b',game,re.I):return None
    return game,dt

def selection(pick):
    return norm(re.sub(r'^total (?:goals|points|runs) by\s+','',str(pick.get('player_name') or pick.get('player') or ''),flags=re.I))

def eligible(pick):
    league=str(pick.get('league') or pick.get('sport') or '').upper()
    ctx=context(pick)
    market=str(pick.get('market') or '')
    if not ctx or league not in PATHS or any(x in market.lower() for x in ('season','standings','fantasy')):return False
    if detect_stat(market)!=STATS[league] or line_of_pick(pick) is None or line_of_pick(pick)<=0:return False
    name=selection(pick)
    return bool(name and (name in {'game','total goals','total points','total runs'} or f' {name} ' in f' {norm(ctx[0])} '))

def match_final_score(pick,event):
    if not eligible(pick):return None
    status=(event.get('status') or {}).get('type') or {}
    if status.get('completed') is not True:return None
    comp=(event.get('competitions') or [{}])[0]
    try:
        start=datetime.fromisoformat(str(comp.get('date') or event.get('date')).replace('Z','+00:00'))
        if start.tzinfo is None or abs((start-context(pick)[1]).total_seconds())>900:return None
    except (ValueError,TypeError):return None
    teams=comp.get('competitors') or []
    if len(teams)!=2 or not event.get('id'):return None
    game=f' {norm(context(pick)[0])} '
    scores=[]; selected=[]
    for item in teams:
        team=item.get('team') or {}
        names={norm(team[k]) for k in ('displayName','shortDisplayName','name','abbreviation') if team.get(k)}
        if not names or not any(f' {name} ' in game for name in names):return None
        try:
            value=float(item['score'])
            if value<0 or not value.is_integer():return None
        except (KeyError,ValueError,TypeError):return None
        scores.append(value)
        if selection(pick) in names:selected.append(value)
    if selection(pick) in {'game','total goals','total points','total runs'}:value=sum(scores)
    elif len(selected)==1:value=selected[0]
    else:return None
    return {'source':'espn_final_team_score','scope':'team_or_game_total','game_id':str(event['id']),
            'game_date':start.date().isoformat(),'start_time_utc':start.isoformat(),'actual_value':value,
            'scoreboard_url':f"https://site.api.espn.com/apis/site/v2/sports/{PATHS[str(pick.get('league') or pick.get('sport')).upper()]}/scoreboard",
            'source_url':f"https://site.api.espn.com/apis/site/v2/sports/{PATHS[str(pick.get('league') or pick.get('sport')).upper()]}/summary?event={event['id']}",
            'event':event}

def main():
    cache={}; results=[]
    for p in select_settlement_picks(limit=20000):
        if str(p.get('status') or p.get('result') or 'pending').lower() not in {'','pending','open','unsettled','none','null'} or not eligible(p):continue
        league=str(p.get('league') or p.get('sport')).upper(); start=context(p)[1]
        if datetime.now(timezone.utc)<start+timedelta(hours=6):continue
        matches={}
        for offset in (-1,0,1):
            day=(start.date()+timedelta(days=offset)).strftime('%Y%m%d'); key=(league,day)
            if key not in cache:
                url=f'https://site.api.espn.com/apis/site/v2/sports/{PATHS[league]}/scoreboard'
                params={'dates':day,'limit':100}
                if league=='NCAAF':params['groups']=80
                cache[key]=(http_json(url,params=params,retries=1) or {}).get('events') or []
            for event in cache[key]:
                match=match_final_score(p,event)
                if match:matches[match['game_id']]=match
        if len(matches)!=1:continue
        evidence=next(iter(matches.values()));value=evidence['actual_value']
        line=line_of_pick(p);side=side_of_pick(p);status=result_for_value(value,line,side);pid=pick_id(p)
        if status=='no_result':continue
        results.append({'result_id':hash_key('pick',pid),'pick_id':pid,'sport':p.get('sport'),'league':league,
                        'player_name':p.get('player_name') or p.get('player'),'normalized_name':norm_name(p.get('player_name') or p.get('player')),
                        'market':p.get('market'),'stat_key':STATS[league],'line':line,'side':side,'actual_value':value,
                        'result':status,'game_id':evidence['game_id'],'settled_at':now_iso(),'pick_raw':p,'result_raw':evidence})
    persist_settlements(results)
    log(f'Exact team/game total settlement: settled={len(results)} scoreboard_dates={len(cache)}')

if __name__=='__main__':main()
