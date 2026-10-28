#!/usr/bin/env python3
"""Read-only classification of every remaining source pick and retained combo leg."""
from collections import Counter
import re
from prop_hunter_shared_utils import select_settlement_picks, select_rows, pick_id, safe_json_write, now_iso
from prop_hunter_settler import (
    _load_relevant_gamelogs, _pick_ready_for_settlement, build_log_index,
    detect_stat, find_gamelog, stat_value, line_of_pick, side_of_pick, result_for_value,
)
from prop_hunter_settler_extras import detect_extra_stat, extra_stat_value, extra_line_of_pick


def classify(pick, logs, index):
    market = str(pick.get('market') or pick.get('prop_type') or '')
    if len(re.findall(r"\b(?:over|under)\s+\d", market.lower())) > 1:
        return 'ambiguous_market_line'
    if any(word in market.lower() for word in ('season ', 'standings', 'fantasy')):
        return 'unsupported_season_or_fantasy_market'
    if '/' in str(pick.get('league') or ''):
        return 'ambiguous_league'
    if not _pick_ready_for_settlement(pick):
        return 'awaiting_game_completion'
    stat, extra = detect_stat(market), detect_extra_stat(market)
    if not stat and not extra:
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
                        'market': p.get('market'), 'reason': reason})
    report = {'generated_at': now_iso(), 'unresolved': len(details), 'counts': dict(counts), 'picks': details}
    safe_json_write('prop_hunter_pending_audit.json', report)
    print(f'Pending audit: unresolved={len(details)} reasons={dict(counts)}', flush=True)


if __name__ == '__main__':
    main()
