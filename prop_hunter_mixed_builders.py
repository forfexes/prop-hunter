"""Confirmed same-game team/player tickets; no multiplied SGP prices."""
from datetime import datetime,timezone
import math,re
from prop_hunter_form_quality import rejection,evidence

def get(o,k,d=None):return o.get(k,d) if isinstance(o,dict) else getattr(o,k,d)
def norm(x):return re.sub('[^a-z0-9]+',' ',str(x or '').lower()).strip()
def stamp(x):
    try:
        d=datetime.fromisoformat(str(x).replace('Z','+00:00'))
        return d.astimezone(timezone.utc) if d.tzinfo else None
    except (ValueError,TypeError):return None

def team_leg_valid(leg):
    raw=leg.get('raw') or {};kind=raw.get('team_builder_market')
    try:line=float(leg['point']);price=float(leg['odds'])
    except (KeyError,TypeError,ValueError):return False
    return (kind in {'moneyline','team_total','game_total','both_over'} and math.isfinite(line) and math.isfinite(price)
        and price>1 and line>=0 and bool(raw.get('combined_quote_id')) and bool(leg.get('event_id'))
        and bool(stamp(leg.get('commence_time'))) and '@' in str(leg.get('game'))
        and leg.get('direction') in {'over','under'}
        and (kind not in {'moneyline','both_over'} or leg.get('direction')=='over')
        and (kind!='moneyline' or (line==.5 and raw.get('tie_rule')=='push'))
        and raw.get('scope')=='full_game_including_ot')

def build(props,Pick,now=None):
    now=now or datetime.now(timezone.utc);out=[];seen=set()
    props=list(props)
    for source in props:
        sf=get(source,'features',{}) or {}
        for q in sf.get('confirmed_builder_quotes',[]) or []:
            if not isinstance(q,dict) or q.get('odds_observed') is not True:continue
            qid=str(q.get('quote_id') or '');start=stamp(q.get('commence_time'));observed=stamp(q.get('observed_at'));expires=stamp(q.get('expires_at'))
            try:odds=float(q['odds'])
            except (KeyError,ValueError,TypeError):continue
            book=str(q.get('bookmaker') or '').lower();sport=str(q.get('sport') or '').upper();game=str(q.get('game') or '');eid=str(q.get('event_id') or '')
            if (not qid or qid in seen or not eid or not book or book!=str(sf.get('bookmaker') or '').lower() or sport not in {'NBA','WNBA','NFL','NHL','MLB','NCAAB','NCAAF'}
                or not start or start<=now or not observed or not 0<=(now-observed).total_seconds()<=1800
                or not expires or expires<=now or not math.isfinite(odds) or odds<=1 or '@' not in game):continue
            legs=[];bad=False;types=set()
            if not isinstance(q.get('legs'),list) or not 2<=len(q['legs'])<=5:continue
            for leg in q['legs']:
                if not isinstance(leg,dict):bad=True;break
                types.add(leg.get('kind'));kind=leg.get('kind')
                try:point=float(leg['point']);price=float(leg['odds'])
                except (KeyError,TypeError,ValueError):bad=True;break
                if not math.isfinite(point) or not math.isfinite(price) or price<=1 or not leg.get('selection_id'):bad=True;break
                item=dict(leg,game=game,sport=sport,league=sport,event_id=eid,commence_time=start.isoformat(),bookmaker=book)
                if kind=='player':
                    matches=[]
                    for prop in props:
                        f=get(prop,'features',{}) or {}
                        try:same_line=abs(float(get(prop,'point'))-point)<1e-6
                        except (TypeError,ValueError):continue
                        if (norm(get(prop,'player'))==norm(leg.get('player')) and norm(get(prop,'market'))==norm(leg.get('market'))
                            and same_line and get(prop,'direction')==leg.get('direction') and abs(float(get(prop,'odds',0))-price)<.011
                            and norm(get(prop,'game'))==norm(game) and str(f.get('bookmaker') or '').lower()==book
                            and str(get(prop,'sport') or '').upper()==sport
                            and str(get(prop,'event_id') or f.get('source_event_id') or f.get('event_id') or '')==eid
                            and stamp(get(prop,'commence_time') or f.get('commence_time'))==start and not rejection(f,point,leg.get('direction'))):matches.append(prop)
                    if len(matches)!=1:bad=True;break
                    item['features']=evidence(get(matches[0],'features',{}))
                elif kind=='team':
                    raw=dict(leg.get('raw') or {},combined_quote_id=qid)
                    item['raw']=raw
                    if not team_leg_valid(item):bad=True;break
                else:bad=True;break
                legs.append(item)
            if bad or types!={'team','player'}:continue
            if len({str(l['selection_id']) for l in legs})!=len(legs):continue
            # Observed ticket price only. No joint probability or EV is invented.
            pick=Pick(type='betbuilder',category='mixed',player=' + '.join(l.get('player','') for l in legs),team='',emoji='🎯',market=f'{len(legs)}-Leg TEAM + PLAYER',direction='over',odds=odds,stake=.05,probability=None,edge_pct=None,ev=None,game=game,
                legs=[f"{l.get('player','')} {l.get('market','')} {l.get('direction','')} {l['point']:g} @{l['odds']:.2f}" for l in legs])
            pick.sport=sport;pick.commence_time=start;pick.event_id=eid;pick.leg_details=legs
            pick.features=dict(odds_observed=True,price_type='bookmaker',combined_odds_observed=True,combined_quote_id=qid,bookmaker=book,combo_scope='same_game',quote_observed_at=observed.isoformat(),quote_expires_at=expires.isoformat())
            out.append(pick);seen.add(qid)
    return out
