#!/usr/bin/env python3
"""Read-only classification of every remaining source pick and retained combo leg."""
from collections import Counter
import re
from datetime import datetime, timezone, timedelta
import os
from prop_hunter_shared_utils import select_settlement_picks, select_rows, pick_id, safe_json_write, now_iso, hash_key, norm_name
from prop_hunter_settler import persist_settlements
from prop_hunter_settler import (
    _load_relevant_gamelogs, _pick_ready_for_settlement, build_log_index,
    detect_stat, find_gamelog, stat_value, line_of_pick, side_of_pick, result_for_value,
)
from prop_hunter_settler_extras import detect_extra_stat, extra_stat_value, extra_line_of_pick


def explicit_nonplayer_scope(pick):
    player = str(pick.get('player_name') or pick.get('player') or '').strip().lower()
    market = str(pick.get('market') or pick.get('prop_type') or '').lower()
    if re.search(r"\bstandings\b", player) or any(word in market for word in ('season ', 'standings', 'fantasy')):
        return 'unsupported_season_or_fantasy_market'
    if player in {'game', 'total goals'} or player.startswith('total goals by '):
        return 'unsupported_team_or_game_market'
    return None


def evidence_context(pick, index):
    """Diagnostic observations only; never relax settlement matching."""
    from prop_hunter_shared_utils import norm_name
    league = str(pick.get('league') or pick.get('sport') or '').upper()
    name = norm_name(pick.get('player_name') or pick.get('player'))
    candidates = [r for r in index.get(name, [])
                  if not league or not r.get('league') or str(r.get('league')).upper() == league]
    dates = sorted({str(r.get('game_date'))[:10] for r in candidates if r.get('game_date')})
    raw = pick.get('raw') if isinstance(pick.get('raw'), dict) else {}
    return {'quoted_game_id': pick.get('game_id') or pick.get('source_game_id'),
            'quoted_kickoff': pick.get('commence_time') or raw.get('commence_time'),
            'quoted_game': pick.get('game') or raw.get('game'),
            'loaded_player_rows': len(candidates),
            'loaded_game_dates': dates}

def classify(pick, logs, index):
    market = str(pick.get('market') or pick.get('prop_type') or '')
    if len(re.findall(r"\b(?:over|under)\s+\d", market.lower())) > 1:
        return 'ambiguous_market_line'
    scope = explicit_nonplayer_scope(pick)
    if scope:
        return scope
    if '/' in str(pick.get('league') or ''):
        return 'ambiguous_league'
    if not _pick_ready_for_settlement(pick):
        return 'awaiting_game_completion'
    stat, extra = detect_stat(market), detect_extra_stat(market)
    if not stat and not extra:
        raw = pick.get('raw') if isinstance(pick.get('raw'), dict) else {}
        if raw.get('type') in {'betbuilder','ladder','acca','lottery'} and any(isinstance(x,dict) for x in raw.get('leg_details') or raw.get('ladder_legs') or []):
            return 'awaiting_combo_legs'
        return 'unmapped_market'
    gl = find_gamelog(pick, logs, aliases={}, log_index=index)
    if not gl:
        return 'no_unique_official_game'
    value = stat_value(gl, stat) if stat else extra_stat_value(gl, extra)
    line = line_of_pick(pick) if stat else extra_line_of_pick(pick, extra)
    if result_for_value(value, line, side_of_pick(pick)) == 'no_result':
        return 'missing_stat_or_line'
    return 'ready_to_settle'


def main():
    picks = [p for p in select_settlement_picks(limit=20000)
             if str(p.get('status') or p.get('result') or 'pending').lower()
             in {'', 'pending', 'open', 'unsettled', 'null', 'none'}]
    results = select_rows('prop_hunter_results', limit=None, order_by='result_id')
    closed = {r.get('pick_id') for r in results if r.get('result') in {'win', 'loss', 'push', 'void'}}
    picks = [p for p in picks if pick_id(p) not in closed]
    logs = _load_relevant_gamelogs(picks)
    index = build_log_index(logs)
    details = []
    counts = Counter()
    for p in picks:
        reason = classify(p, logs, index)
        counts[reason] += 1
        details.append({'pick_id': pick_id(p), 'source': p.get('_source_table'),
                        'date': p.get('date'), 'league': p.get('league') or p.get('sport'),
                        'player': p.get('player') or p.get('player_name'),
                        'market': p.get('market'), 'reason': reason,
                        'evidence': evidence_context(p, index) if reason == 'no_unique_official_game' else None})
    # ─── AUTO-VOID: terminale Altlasten aufräumen ───────────────────────────
    # Picks mit einem endgültigen (nicht-wartenden) Grund, deren Spiel lange vorbei
    # ist, werden nie gradebar (DNP/verletzt, Fantasy/Season-Futures, Team-Märkte,
    # doppelte Linien). Sie bleiben sonst ewig pending und verfälschen die Statistik.
    # Nur mit PH_AUTO_VOID_STALE=1 aktiv; Karenz über PH_AUTO_VOID_DAYS (Default 3).
    TERMINAL = {
        'unsupported_season_or_fantasy_market', 'unsupported_team_or_game_market',
        'ambiguous_market_line', 'ambiguous_league', 'unmapped_market',
        'no_unique_official_game',
    }
    if os.getenv('PH_AUTO_VOID_STALE', '0').lower() in {'1', 'true', 'yes', 'on'}:
        grace_days = int(os.getenv('PH_AUTO_VOID_DAYS', '3'))
        cutoff = datetime.now(timezone.utc) - timedelta(days=grace_days)
        by_id = {pick_id(p): p for p in picks}
        void_rows = []
        for d in details:
            if d['reason'] not in TERMINAL:
                continue
            p = by_id.get(d['pick_id'])
            if not p:
                continue
            # Spieldatum bestimmen (commence_time, sonst date) — nur alte voiden
            ref = str(p.get('commence_time') or p.get('date') or p.get('sent_date') or '')
            try:
                dt = datetime.fromisoformat(ref.replace('Z', '+00:00'))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                try:
                    dt = datetime.fromisoformat(str(p.get('date'))[:10]).replace(tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    continue
            if dt > cutoff:
                continue  # noch zu frisch — in Ruhe lassen
            pid = d['pick_id']
            void_rows.append({
                'result_id': hash_key('pick', pid),
                'pick_id': pid,
                'sport': p.get('sport') or p.get('league'),
                'league': p.get('league') or p.get('sport'),
                'player_name': p.get('player_name') or p.get('player'),
                'normalized_name': norm_name(p.get('player_name') or p.get('player')),
                'market': p.get('market') or p.get('prop_type') or p.get('selection'),
                'stat_key': None, 'line': None, 'side': None, 'actual_value': None,
                'result': 'void', 'game_id': p.get('game_id') or p.get('source_game_id'),
                'settled_at': now_iso(), 'pick_raw': p,
                'result_raw': {'void_reason': d['reason'], 'auto_void': True,
                               'grace_days': grace_days},
            })
        if void_rows:
            persist_settlements(void_rows)
            vc = Counter(r['result_raw']['void_reason'] for r in void_rows)
            print(f'Auto-void: {len(void_rows)} stale picks voided reasons={dict(vc)}', flush=True)
        else:
            print('Auto-void: no stale terminal picks past grace window', flush=True)

    report = {'generated_at': now_iso(), 'unresolved': len(details), 'counts': dict(counts), 'picks': details}
    safe_json_write('prop_hunter_pending_audit.json', report)
    print(f'Pending audit: unresolved={len(details)} reasons={dict(counts)}', flush=True)


if __name__ == '__main__':
    main()
