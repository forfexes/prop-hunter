#!/usr/bin/env python3
"""PROP HUNTER 13.10.2 — daily-control + keyless market/line hardening."""
from pathlib import Path as _Path
_core=_Path(__file__).with_name('prophunter_core_1392.py');_src=_core.read_text(encoding='utf-8')
for marker in ('if __name__ == "__main__":',"if __name__=='__main__':",'if __name__=="__main__":'):
    if marker in _src:_src=_src.rsplit(marker,1)[0];break
exec(compile(_src,str(_core),'exec'),globals(),globals())
PH_RUNTIME_VERSION='13.10.1-KEYLESS-HARDENED'

try:
    import prop_hunter_builder_engine as _ph_builder
    from prop_hunter_quote_guard import probability_sane as _probability_sane
    _candidate_probability_base=_ph_builder._candidate_probability
    def _candidate_probability_guarded(obj):
        odds=_ph_builder._odds(obj);feats=_ph_builder._features(obj);raw_prob=None
        for key in ('calibrated_prob','fair_prob','model_prob','hit_prob','proj_prob','probability','gamelog_fair_prob'):
            value=feats.get(key)
            if value is not None:
                raw_prob=_ph_builder.to_float(value)
                if raw_prob is not None:break
        if raw_prob is None:raw_prob=_ph_builder.to_float(getattr(obj,'probability',None))
        if raw_prob is not None and odds>1.001 and not _probability_sane(raw_prob,odds):return None
        return _candidate_probability_base(obj)
    _ph_builder._candidate_probability=_candidate_probability_guarded
except Exception:pass

try:
    from prop_hunter_quote_guard import canonical_market as _canonical_market, probability_sane as _prob_sane
    _enrich_gamelogs_fairprob_base=enrich_gamelogs_fairprob
    def enrich_gamelogs_fairprob(props):
        before={}
        for p in props or []:
            feats=dict(getattr(p,'features',{}) or {})
            before[id(p)]=(feats.get('fair_prob'),feats.get('fair_prob_source'),getattr(p,'enrichment',None))
            try:p.market=_canonical_market(getattr(p,'market',''))
            except Exception:pass
        out=_enrich_gamelogs_fairprob_base(props)
        for p in out or []:
            feats=dict(getattr(p,'features',{}) or {})
            fp=feats.get('fair_prob');odds=getattr(p,'odds',None)
            if fp is None or _prob_sane(fp,odds):continue
            old_prob,old_src,old_enrichment=before.get(id(p),(None,None,None))
            if old_prob is not None and _prob_sane(old_prob,odds):
                feats['fair_prob']=old_prob
                if old_src is not None:feats['fair_prob_source']=old_src
            else:
                feats.pop('fair_prob',None);feats.pop('fair_prob_source',None)
            for key in ('gamelog_l10_rate','gamelog_n','gamelog_dd_rate'):feats.pop(key,None)
            feats['gamelog_prob_rejected']='market_gap_guard';p.features=feats
            if old_enrichment is not None:p.enrichment=old_enrichment
        return out
except Exception:pass

def _snapshot_market_key(row):
    try:
        from prop_hunter_market_consensus import _canon_market
        return _canon_market(row.get('market_key') or row.get('market'))
    except Exception:return str(row.get('market_key') or row.get('market') or '').lower()
def _snapshot_event_key(row):
    try:
        from prop_hunter_market_consensus import _event_key
        return _event_key(row)
    except Exception:return str(row.get('source_event_id') or '')
def fetch_snapshot_props(sport_filter=None):
    c=_sb_read()
    if c is None:return []
    try:
        cutoff=(datetime.now(timezone.utc)-timedelta(hours=18)).isoformat();fields=('sport,league,source_event_id,player_name,market,market_key,direction,line,odds_decimal,commence_time,created_at,home_team,away_team,bookmaker,source,raw')
        try:res=c.table('prop_hunter_prop_snapshots').select(fields).gte('created_at',cutoff).limit(10000).execute()
        except Exception:
            fields=fields.rsplit(',raw',1)[0];res=c.table('prop_hunter_prop_snapshots').select(fields).gte('created_at',cutoff).limit(10000).execute()
        rows=list(res.data or [])
        try:
            from prop_hunter_quote_guard import sanitize_row,probability_sane
            rows=[safe for r in rows if (safe:=sanitize_row(r)) is not None]
        except Exception:probability_sane=lambda p,o:True
        try:
            from prop_hunter_market_consensus import enrich as _enrich,fair_prob_for as _fair
            rows=_enrich(rows)
        except Exception as exc:log.warning('snapshot consensus unavailable: %s',exc);_fair=lambda r:None
        now_month=datetime.now(timezone.utc).month;active={'MLB','WNBA','NCAAF'}
        if now_month>=9 or now_month<=2:active|={'NFL','NBA','NHL','NCAAB'}
        if 4<=now_month<=6:active|={'NBA','NHL'}
        if now_month>=9 or now_month<=6:active|={'EUROLEAGUE'}
        season_markers=('season','futures','to win','mvp','champion','award','regular season','playoff','total wins','make the','division','conference','over/under wins');best={}
        for r in rows:
            sport=str(r.get('sport') or r.get('league') or '').upper();player=str(r.get('player_name') or '').strip();market=str(r.get('market') or r.get('market_key') or '').strip();direction=str(r.get('direction') or '').lower().strip();line=r.get('line')
            # Snapshot freshness alone is not enough: a recently re-ingested stale
            # row must never become a new pick after its actual event already started.
            ct_raw=r.get('commence_time')
            if not ct_raw:continue
            try:
                ct_check=datetime.fromisoformat(str(ct_raw).replace('Z','+00:00'))
                if ct_check.tzinfo is None:ct_check=ct_check.replace(tzinfo=timezone.utc)
                now_utc=datetime.now(timezone.utc)
                if ct_check < now_utc-timedelta(minutes=5):continue
                if ct_check > now_utc+timedelta(hours=float(os.getenv('PH_SNAPSHOT_EVENT_HORIZON_HOURS','72'))):continue
            except Exception:continue
            try:odds=float(r.get('odds_decimal'))
            except Exception:continue
            if not(player and market and line is not None and 1.01<odds<75):continue
            if sport_filter and sport_filter.lower() not in sport.lower():continue
            if sport and sport not in active:continue
            if any(x in market.lower() for x in season_markers):continue
            if direction not in {'over','under'}:continue
            book=str(r.get('bookmaker') or r.get('source') or '').lower().strip()
            if not book:continue
            key=(sport,_snapshot_event_key(r),player.lower(),_snapshot_market_key(r),round(float(line),4),direction);cur=best.get(key)
            if cur is None or odds>float(cur.get('odds_decimal') or 0):best[key]=r
        try:
            from prop_hunter_market_intelligence import movement_index,market_key as _mi_key,consensus_count
            _movement=movement_index(rows)
        except Exception:_movement={};_mi_key=lambda row:();consensus_count=lambda row,rows:0
        emoji_map={'NBA':'🏀','WNBA':'🏀','MLB':'⚾','NFL':'🏈','NHL':'🏒','NCAAB':'🏀','NCAAF':'🏈','EUROLEAGUE':'🏀'};out=[];fair_rejected=0
        for r in best.values():
            sport=str(r.get('sport') or r.get('league') or '').upper();book=str(r.get('bookmaker') or r.get('source') or '').lower();raw=r.get('raw') if isinstance(r.get('raw'),dict) else {};cons=raw.get('consensus') if isinstance(raw.get('consensus'),dict) else {};fair=_fair(r);odds=float(r.get('odds_decimal'))
            feats={'odds_observed':True,'price_type':'bookmaker','bookmaker':book,'source':r.get('source') or book,'sport':sport,'league':sport,'source_event_id':r.get('source_event_id'),'commence_time':r.get('commence_time'),'home_team':r.get('home_team'),'away_team':r.get('away_team'),'event_market':bool(raw.get('event_market')),'consensus_sources':cons.get('source_count') or consensus_count(r,rows),'consensus_books':cons.get('book_count') or 1,'paired_book_count':cons.get('paired_book_count') or 0,'consensus_fair_method':cons.get('fair_method'),**(_movement.get(_mi_key(r),{}) or {})}
            if fair is not None and probability_sane(fair,odds):feats['fair_prob']=round(float(fair),6);feats['fair_prob_source']='market_no_vig_consensus'
            elif fair is not None:fair_rejected+=1;feats['fair_prob_rejected']=round(float(fair),6);feats['fair_prob_reject_reason']='market_gap_guard'
            ct=None
            if r.get('commence_time'):
                try:ct=datetime.fromisoformat(str(r.get('commence_time')).replace('Z','+00:00'))
                except Exception:pass
            try:out.append(Prop(player=r.get('player_name'),market=r.get('market') or r.get('market_key'),odds=odds,point=float(r.get('line')),sport=sport,emoji=emoji_map.get(sport,'🎯'),game=f"{r.get('away_team','')} @ {r.get('home_team','')}",home=r.get('home_team') or None,away=r.get('away_team') or None,commence_time=ct,direction=r.get('direction'),enrichment=f'src:{book}',features=feats))
            except Exception:continue
        if out:log.info('Snapshot sportsbook props: %d best-price sides | no-vig fair=%d | rejected fair=%d',len(out),sum(1 for p in out if (getattr(p,'features',{}) or {}).get('fair_prob') is not None),fair_rejected)
        return out
    except Exception as exc:log.warning('snapshot props 13.10.1: %s',exc);return []
if __name__=='__main__':raise SystemExit(main())
