"""Exact-line recent form evidence shared by delivery and builder candidates."""
import math

def numeric(x):
    try:
        x=float(x)
        return x if math.isfinite(x) else None
    except (TypeError,ValueError):return None

def profile(values,line,direction):
    values=list(values[:15]);result={'version':1,'line':float(line),'direction':direction}
    success=lambda v: v<float(line) if direction=='under' else v>float(line)
    for n in (5,10,15):
        part=values[:n]
        result[f'l{n}']={'n':len(part),'hits':sum(success(v) for v in part),'avg':round(sum(part)/len(part),4) if part else None}
    # Describe recent changes without manufacturing a new probability.
    previous=values[5:15]
    result['previous']={'n':len(previous),'hits':sum(success(v) for v in previous)}
    return result

def rejection(features,line,direction):
    f=features or {}
    direction={"yes":"over","no":"under"}.get(direction,direction)
    if f.get('gamelog_prob_rejected'):return 'rejected_model_probability'
    n=numeric(f.get('gamelog_l15_n',f.get('gamelog_n')))
    if n is None or n<6:return 'insufficient_current_games'
    if line is None:
        if f.get('gamelog_dd_rate') is None:return 'missing_exact_line'
        line=.5
    verified=numeric(f.get('gamelog_l15_line'))
    if verified is None or numeric(line) is None or abs(verified-float(line))>1e-6:return 'mismatched_form_line'
    if str(f.get('gamelog_l15_direction') or '').lower()!=direction:return 'mismatched_form_side'
    p=f.get('recent_form') or {}
    if p:
        if numeric(p.get('line'))!=verified or p.get('direction')!=direction:return 'mismatched_recent_form'
        # Conservative policy: 0/5 or 1/5 after >=60% in at least five prior games.
        # This is a selection rule, not a statistically validated probability model.
        recent=p.get('l5') or {};prev=p.get('previous') or {}
        if recent.get('n')==5 and recent.get('hits',5)<=1 and prev.get('n',0)>=5:
            if prev.get('hits',0)/prev['n']>=.6:return 'recent_form_deterioration'
    return None

def filter_singles(picks):
    kept=[];rejected={}
    for pick in picks:
        if getattr(pick,'type',None)!='single':kept.append(pick);continue
        f=getattr(pick,'features',{}) or {}
        reason=rejection(f,getattr(pick,'point',None),str(getattr(pick,'direction','') or '').lower())
        if reason:rejected[reason]=rejected.get(reason,0)+1
        else:kept.append(pick)
    return kept,rejected

def evidence(features):
    return {k:v for k,v in (features or {}).items() if k in {
        'recent_form','gamelog_n','gamelog_l15_n','gamelog_l15_line',
        'gamelog_l15_direction','gamelog_l15_hits','gamelog_dd_rate',
        'gamelog_prob_rejected','form_window_policy','form_last_game_date',
        'form_reference_date','form_season_start'}}

def filter_tickets(picks):
    picks,counts=filter_singles(picks)
    kept=[]
    for p in picks:
        if getattr(p,'type',None)=='single':kept.append(p);continue
        legs=getattr(p,'leg_details',None) or []
        reason='missing_leg_form' if len(legs)<2 else None
        for leg in legs:
            if reason:break
            reason=rejection(leg.get('features'),leg.get('point'),str(leg.get('direction') or '').lower())
        if reason:counts[reason]=counts.get(reason,0)+1
        else:kept.append(p)
    return kept,counts
