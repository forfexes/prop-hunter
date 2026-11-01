"""Bounded ESPN NFL settlement fallback. Missing observations stay missing."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import math
import re
from prop_hunter_shared_utils import http_json, norm_name, log
from prop_hunter_scan_dates import select_scan_dates

BASE='https://site.api.espn.com/apis/site/v2/sports/football/nfl/'

def timestamp(value):
    try:
        d=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return d.astimezone(timezone.utc) if d.tzinfo else None
    except (ValueError,TypeError):return None

def final(event):
    status=(event.get('status') or {}).get('type') or {}
    return status.get('completed') is True and status.get('state')=='post'

def pick_start(p):
    raw=p.get('raw') if isinstance(p.get('raw'),dict) else {}
    return timestamp(p.get('commence_time') or raw.get('commence_time'))

def event_matches(event,p):
    start=timestamp(event.get('date'))
    if not start:return False
    quoted=pick_start(p)
    if quoted and abs((start-quoted).total_seconds())>900:return False
    raw=p.get('raw') if isinstance(p.get('raw'),dict) else {}
    hint=str(p.get('game') or raw.get('game') or '')
    parts=re.split(r'\s+(?:@|vs\.?|at)\s+',hint,flags=re.I)
    if len(parts)!=2:return quoted is not None
    day=str(p.get('date') or p.get('sent_date') or '')[:10]
    if not quoted and day not in {start.date().isoformat(),start.astimezone(ZoneInfo('America/New_York')).date().isoformat()}:return False
    comps=(event.get('competitions') or [{}])[0].get('competitors') or []
    aliases=[]
    for comp in comps:
        team=comp.get('team') or {}
        aliases.append({norm_name(team.get(k) or '') for k in ('displayName','shortDisplayName','abbreviation')} |
                       {norm_name(str(team.get('abbreviation') or '')+' '+str(team.get('name') or ''))})
    return len(aliases)==2 and any(norm_name(parts[0]) in aliases[i] and norm_name(parts[1]) in aliases[1-i] for i in (0,1))

def number(value):
    try:
        x=float(str(value).replace(',',''))
        return x if math.isfinite(x) else None
    except (ValueError,TypeError):return None

MAP={
 'passing':{'YDS':'passing_yards','TD':'passing_touchdowns','INT':'interceptions'},
 'rushing':{'YDS':'rushing_yards','CAR':'rushing_attempts','TD':'rushing_touchdowns'},
 'receiving':{'YDS':'receiving_yards','REC':'receptions','TGTS':'targets','TD':'receiving_touchdowns'},
}

def summary_rows(summary,event,wanted):
    # Recheck the official event status in the summary itself.
    header=summary.get('header') or {}
    competitions=header.get('competitions') or []
    if str(header.get('id') or '')!=str(event.get('id')) or not competitions or not final(competitions[0]):return []
    start=timestamp(event.get('date'))
    observed=timestamp(competitions[0].get('date'))
    if not start or not observed or abs((start-observed).total_seconds())>900:return []
    athletes={}; names={}; conflicts=set()
    for team in (summary.get('boxscore') or {}).get('players') or []:
        for group in team.get('statistics') or []:
            category=group.get('name');mapping=MAP.get(category)
            if not mapping:continue
            labels=group.get('labels') or []
            for athlete in group.get('athletes') or []:
                info=athlete.get('athlete') or {}; aid=str(info.get('id') or '')
                name=info.get('displayName') or ''; nk=norm_name(name)
                stats=athlete.get('stats') or []
                if nk not in wanted or not aid or athlete.get('didNotPlay') is True or not stats or len(labels)!=len(stats):continue
                names.setdefault(nk,set()).add(aid)
                row=athletes.setdefault(aid,dict(player_name=name,normalized_name=nk,team=(team.get('team') or {}).get('abbreviation'),raw={'athlete_id':aid,'start_time_utc':event.get('date'),'categories':{}}))
                sm=dict(zip(labels,stats));row['raw']['categories'][category]=sm
                for key,column in mapping.items():
                    value=number(sm.get(key))
                    if value is None:continue
                    if column in row and row[column]!=value:conflicts.add(aid)
                    row[column]=value
    rows=[]
    for aid,row in athletes.items():
        if aid in conflicts or len(names[row['normalized_name']])!=1:continue
        if not any(key in row for mapping in MAP.values() for key in mapping.values()):continue
        # Do not assume absent rushing/receiving categories imply zero TDs.
        if 'rushing_touchdowns' in row and 'receiving_touchdowns' in row:
            total=row['rushing_touchdowns']+row['receiving_touchdowns']
            row.update(touchdowns=total,anytime_td=float(total>=1),two_plus_td=float(total>=2),three_plus_td=float(total>=3))
        day=start.astimezone(ZoneInfo('America/New_York')).date()
        row.update(sport='AMERICAN_FOOTBALL',league='NFL',season=str(day.year if day.month>=8 else day.year-1),game_id=str(event['id']),source_game_id=str(event['id']),game_date=day.isoformat(),source='espn_nfl_summary')
        rows.append(row)
    return rows

def collect(picks,primary,get=http_json,max_dates=5,max_events=8):
    eligible=[p for p in picks if str(p.get('league') or p.get('sport') or '').upper()=='NFL' and str(p.get('status') or p.get('result') or 'pending').lower() in {'pending','open','unsettled'}]
    by_date={}
    for p in eligible:
        start=pick_start(p)
        try:day=(start or datetime.fromisoformat(str(p.get('date') or p.get('sent_date'))[:10])).date()
        except (ValueError,TypeError):continue
        for offset in (-1,0,1):by_date.setdefault((day+timedelta(days=offset)).strftime('%Y%m%d'),[]).append(p)
    events={};matches={}
    for day,ps in select_scan_dates(by_date,max_dates,datetime.now(timezone.utc).date()):
        board=get(BASE+'scoreboard',params={'dates':day,'limit':100})
        if board is None:raise RuntimeError('NFL ESPN scoreboard unavailable')
        for ev in board.get('events') or []:
            if not final(ev) or not ev.get('id'):continue
            for p in ps:
                if event_matches(ev,p):
                    key=(norm_name(p.get('player_name') or p.get('player') or ''),pick_start(p),str(p.get('date') or p.get('sent_date') or ''))
                    matches.setdefault(key,set()).add(str(ev['id']));events[str(ev['id'])]=ev
    requests={}
    for (name,_,_),ids in matches.items():
        if name and len(ids)==1:requests.setdefault(next(iter(ids)),set()).add(name)
    if len(requests)>max_events:raise RuntimeError('NFL ESPN event budget exceeded')
    native={(norm_name(r.get('player_name') or ''),r.get('game_date')) for r in primary}
    rows=[]
    for eid,names in requests.items():
        summary=get(BASE+'summary',params={'event':eid})
        if summary is None:raise RuntimeError('NFL ESPN summary unavailable')
        for row in summary_rows(summary,events[eid],names):
            if (row['normalized_name'],row['game_date']) not in native:rows.append(row)
    log(f'NFL ESPN fallback: picks={len(eligible)} events={len(requests)} added={len(rows)}')
    return rows
