#!/usr/bin/env python3
"""PROP HUNTER 13.10.1 keyless-first multi-source orchestrator."""
from pathlib import Path as _Path
_core_path=_Path(__file__).with_name('prop_hunter_source_orchestrator_core_1392.py')
_src=_core_path.read_text(encoding='utf-8')
_src=_src.rsplit('if __name__ == "__main__":',1)[0]
exec(compile(_src,str(_core_path),'exec'),globals(),globals())

_core_normalise=_normalise
def _normalise(row,source):
    out=_core_normalise(row,source)
    if out is None:return None
    try:
        from prop_hunter_quote_guard import sanitize_row
        return sanitize_row(out)
    except Exception:return out

def _row_key(row):
    return str(row.get('snapshot_id') or hash_key(row.get('source'),row.get('bookmaker'),row.get('sport'),row.get('source_event_id') or row.get('game_id'),row.get('player_name'),row.get('market_key') or row.get('market'),row.get('direction'),row.get('line'),row.get('odds_decimal'),row.get('period'),row.get('is_live')))

def _season_active_sports(sports):
    month=datetime.now(timezone.utc).month;active=[]
    for sport in sports:
        if sport=='MLB' and 3<=month<=11:active.append(sport)
        elif sport=='WNBA' and 5<=month<=10:active.append(sport)
        elif sport=='NFL' and (month>=8 or month<=2):active.append(sport)
        elif sport=='NBA' and (month>=9 or month<=6):active.append(sport)
        elif sport=='NHL' and (month>=9 or month<=6):active.append(sport)
        elif sport=='NCAAB' and (month>=10 or month<=4):active.append(sport)
        elif sport=='NCAAF' and (month>=8 or month<=1):active.append(sport)
        elif sport=='EUROLEAGUE' and (month>=9 or month<=6):active.append(sport)
    return active or list(sports)

def _direct_jobs(sports):
    import prop_hunter_odds_pp_ud as ppud
    active=_season_active_sports(sports);jobs=[]
    try:
        import prop_hunter_keyless_books as kb
        try:
            from prop_hunter_keyless_extensions import install as _install_keyless_extensions
            _install_keyless_extensions(kb)
        except Exception as exc:
            warn(f'keyless market extensions unavailable: {exc}')
        if kb.configured():
            for sport in active:
                jobs.extend([
                    (f'draftkings_direct_{sport.lower()}',lambda s=sport:kb.fetch_draftkings_props(s)),
                    (f'fanduel_direct_{sport.lower()}',lambda s=sport:kb.fetch_fanduel_props(s)),
                    (f'bovada_direct_{sport.lower()}',lambda s=sport:kb.fetch_bovada_props(s)),
                    (f'betrivers_direct_{sport.lower()}',lambda s=sport:kb.fetch_betrivers_props(s)),
                ])
    except Exception as exc:warn(f'keyless direct books unavailable: {exc}')
    try:
        import prop_hunter_kambi as kambi
        kambi.SPORT_PATHS.setdefault('EUROLEAGUE',('basketball/euroleague','basketball'))
        if kambi.configured():
            for sport in active:jobs.append((f'kambi_{sport.lower()}',lambda s=sport:kambi.fetch_kambi_props(s,max_events=max(1,int(os.getenv('PH_KAMBI_MAX_EVENTS','3'))))))
    except Exception as exc:warn(f'Kambi adapter unavailable: {exc}')
    try:
        import prop_hunter_1xbet as xb
        xb.SPORT_IDS.setdefault('EUROLEAGUE',3)
        _xb_league_ok=xb._league_ok
        def _xb_league_ok_ext(sport,row):
            if sport=='EUROLEAGUE':
                text=' '.join(str(row.get(k) or '') for k in ('LE','L','League','O1','O2','HomeTeam','AwayTeam')).lower()
                return 'euroleague' in text or 'euro league' in text
            return _xb_league_ok(sport,row)
        xb._league_ok=_xb_league_ok_ext
        if xb.configured():
            for sport in active:jobs.append((f'1xbet_{sport.lower()}',lambda s=sport:xb.fetch_1xbet_props(s,max_events=max(1,int(os.getenv('PH_1XBET_MAX_EVENTS','2'))))))
    except Exception as exc:warn(f'1xBet adapter unavailable: {exc}')
    try:
        import prop_hunter_sgo as sgo
        if sgo.configured():
            keys={'MLB':'baseball_mlb','NBA':'basketball_nba','WNBA':'basketball_wnba','NFL':'americanfootball_nfl','NHL':'icehockey_nhl','NCAAB':'basketball_ncaab','NCAAF':'americanfootball_ncaaf','EUROLEAGUE':'basketball_euroleague'}
            for sport in active:
                key=keys.get(sport)
                if key:jobs.append((f'sportsgameodds_{sport.lower()}',lambda s=sport:sgo.fetch_sgo_props(keys[s])))
    except Exception as exc:warn(f'SGO adapter unavailable: {exc}')
    try:
        import prop_hunter_opticodds as oo
        try:oo.SUPPORTED.add('EUROLEAGUE')
        except Exception:pass
        if oo.configured():
            for sport in active:jobs.append((f'opticodds_{sport.lower()}',lambda s=sport:oo.fetch_opticodds_props(s,max_fixtures=max(1,int(os.getenv('PH_OPTICODDS_MAX_FIXTURES','5'))))))
    except Exception as exc:warn(f'OpticOdds adapter unavailable: {exc}')
    try:
        import prop_hunter_oddspapi as op
        if op.configured():
            keys={'MLB':'baseball_mlb','NBA':'basketball_nba','WNBA':'basketball_wnba','NFL':'americanfootball_nfl','NHL':'icehockey_nhl','NCAAB':'basketball_ncaab','NCAAF':'americanfootball_ncaaf','EUROLEAGUE':'basketball_euroleague'}
            for sport in active:
                key=keys.get(sport)
                if key:jobs.append((f'oddspapi_{sport.lower()}',lambda s=sport:op.fetch_oddspapi_props(keys[s],max_events=max(1,int(os.getenv('PH_ODDSPAPI_MAX_EVENTS','2'))))))
    except Exception as exc:warn(f'OddsPapi adapter unavailable: {exc}')
    try:
        import prop_hunter_parlayapi as pa
        if pa.configured():
            for sport in active:jobs.append((f'parlayapi_{sport.lower()}',lambda s=sport:pa.fetch_parlayapi_props(s)))
    except Exception as exc:warn(f'ParlayAPI adapter unavailable: {exc}')
    try:
        import prop_hunter_propline as pl
        if pl.configured():
            for sport in active:jobs.append((f'propline_{sport.lower()}',lambda s=sport:pl.fetch_propline_props(s)))
    except Exception as exc:warn(f'PropLine adapter unavailable: {exc}')
    try:
        import prop_hunter_oddsapi_io as oai
        if oai.configured():
            for sport in active:jobs.append((f'oddsapi_io_{sport.lower()}',lambda s=sport:oai.fetch_oddsapi_io_props(s)))
    except Exception:pass
    jobs.extend([('underdog',ppud.fetch_underdog),('sleeper',ppud.fetch_sleeper)])
    if str(os.getenv('PH_SKIP_BLOCKED_FREE','1')).lower() not in {'1','true','yes','on'}:
        for sport in active:jobs.append((f'prizepicks_{sport.lower()}',lambda s=sport:ppud.fetch_prizepicks(s)))
    return jobs

def _coverage(rows,sport):
    sport=str(sport or '').upper();priced=[r for r in rows if str(r.get('sport') or r.get('league') or '').upper()==sport and (to_float(r.get('odds_decimal')) or 0)>1];books={str(r.get('bookmaker') or r.get('source') or '').lower() for r in priced};pairs={}
    for r in priced:
        side=str(r.get('direction') or '').lower()
        if side not in {'over','under'}:continue
        key=(str(r.get('bookmaker') or r.get('source') or '').lower(),str(r.get('player_name') or '').lower(),str(r.get('market_key') or r.get('market') or '').lower(),str(r.get('line')));pairs.setdefault(key,set()).add(side)
    return len(priced),len(books),sum(1 for sides in pairs.values() if {'over','under'}<=sides)

def collect(sport_filter=None,mode='fast'):
    sports=[sport_filter.upper()] if sport_filter else list(SPORTS);sports=[s for s in sports if s in {'MLB','NBA','WNBA','NFL','NHL','NCAAB','NCAAF','EUROLEAGUE'}];max_cache_age=8 if mode=='fast' else 30;all_rows=[];audits=[]
    row_target=max(1,int(os.getenv('PH_DIRECT_ROWS_PER_SPORT_TARGET','50')));book_target=max(1,int(os.getenv('PH_DIRECT_BOOK_TARGET','5')));pair_target=max(1,int(os.getenv('PH_DIRECT_PAIR_TARGET','15')));source_budget=max(30,int(os.getenv('PH_SOURCE_BUDGET_SEC','165')));started=time.monotonic()
    fallback_prefixes=('1xbet_','sportsgameodds_','opticodds_','oddspapi_','parlayapi_','propline_','oddsapi_io_')
    for source,fn in _direct_jobs(sports):
        if time.monotonic()-started>source_budget:
            audits.append(_audit('source_budget','budget_exhausted',[],time.monotonic()-started,f'budget={source_budget}s'));print(f'source budget exhausted after {source_budget}s',flush=True);break
        source_sport=source.rsplit('_',1)[-1].upper() if '_' in source else ''
        if source.startswith(fallback_prefixes) and source_sport in sports:
            nrows,nbooks,npairs=_coverage(all_rows,source_sport)
            if nrows>=row_target and nbooks>=book_target and npairs>=pair_target:
                audit=_audit(source,'skipped_covered',[],0.0,f'earlier free coverage rows={nrows} books={nbooks} paired={npairs}');audits.append(audit);print(f'source {source}: 0 | skipped_covered rows={nrows} books={nbooks} paired={npairs}',flush=True);continue
        rows,audit=_call(source,fn,max_cache_age);all_rows.extend(rows);audits.append(audit);print(f'source {source}: {len(rows)} | {audit["status"]}',flush=True)
    direct_odds_rows=sum(1 for r in all_rows if (to_float(r.get('odds_decimal')) or 0)>1);priced_pickem_rows=sum(1 for r in all_rows if to_float(r.get('higher_odds_decimal')) and to_float(r.get('lower_odds_decimal')));print(f'direct coverage: sportsbook={direct_odds_rows} priced_pickem={priced_pickem_rows}',flush=True)
    browser_enabled=str(os.getenv('PH_BROWSER_ENABLED','0')).lower() in {'1','true','yes','on'};run_browser=browser_enabled and (mode in {'all','browser'} or (mode=='fast' and direct_odds_rows==0))
    if run_browser:
        books=[x.strip() for x in os.getenv('PH_FAST_BROWSER_BOOKS','bet365').split(',') if x.strip()];max_browser=int(os.getenv('PH_FAST_BROWSER_JOBS','2')) if mode=='fast' else int(os.getenv('PH_MAX_BROWSER_JOBS','12'))
        for source,fn in _browser_jobs(_season_active_sports(sports),books)[:max_browser]:
            rows,audit=_call(source,fn,max_cache_age);all_rows.extend(rows);audits.append(audit)
    dedup={}
    for row in all_rows:dedup[_row_key(row)]=row
    rows=list(dedup.values())
    try:
        from prop_hunter_market_consensus import enrich as _enrich
        rows=_enrich(rows)
    except Exception as exc:warn(f'market consensus skipped: {exc}')
    safe_json_write(OUT_FILE,rows);safe_json_write('prop_hunter_source_health.json',audits);_upsert_chunks('prop_hunter_prop_snapshots',_snapshot_rows_for_db(rows),conflict='snapshot_id',size=200)
    audit_db=[{'source_name':a.get('item_key'),'sport':','.join((a.get('payload') or {}).get('sports',[])),'check_type':'source_health','status':a.get('status'),'message':a.get('message'),'latency_ms':int(float((a.get('payload') or {}).get('elapsed_s',0))*1000),'raw':a.get('payload') or {}} for a in audits];_upsert_chunks('prop_hunter_source_audit',audit_db,conflict=None,size=100);persist_registry();print(f'ALL SOURCES 13.10.1: {len(rows)} unique rows from {len(audits)} checks',flush=True);return rows

if __name__=='__main__':main()
