#!/usr/bin/env python3
"""Offline regressions for historical debt, source mirroring and ladder grading."""
from unittest.mock import patch, MagicMock
from pathlib import Path
from prop_hunter_settler import detect_stat, stat_value, result_for_value, persist_settlements
from prop_hunter_shared_utils import _normalise_pick_row, select_settlement_picks
import prop_hunter_results_mlb as mlb
import prophunter_results as reporter
from prop_hunter_learning_update import unique_results


def main():
    for market, expected in [('pa Over 18.5','pa'), ('PR Under 19.5','pr'),
                             ('passing_yards Over 200.5','passing_yards'),
                             ('Home Run','home_runs'), ('3-PT Made Over 1.5','threes_made')]:
        assert detect_stat(market) == expected, market
    assert stat_value({'points': 20, 'assists': 4}, 'pa') == 24
    assert result_for_value(False, .5, 'under') == 'win'
    assert result_for_value(None, .5, 'under') == 'no_result'
    row = _normalise_pick_row({'id': 1, 'result': 'loss', 'status': 'pending'}, 'prop_picks')
    assert row['status'] == row['result'] == 'loss'

    sb = MagicMock()
    result = {'result_id': 'r', 'pick_raw': {'dedup_key': 'd'}, 'result': 'win'}
    with patch('prop_hunter_settler.supabase_client', return_value=sb), patch('prop_hunter_settler.mark_source_pick_settled') as mirror:
        sb.table.return_value.upsert.return_value.execute.side_effect = RuntimeError('write failed')
        try:
            persist_settlements([result])
        except RuntimeError:
            pass
        else:
            raise AssertionError('result write failure must propagate')
        mirror.assert_not_called()
        sb.table.return_value.upsert.return_value.execute.side_effect = None
        persist_settlements([result])
        mirror.assert_called_once_with(result['pick_raw'], 'win')

    history = [{'date': '2026-10-22', 'kombis': [{'type': 'ladder', 'player': 'Only Ladder', 'sport': 'NBA',
                'leg_details': [{'market': '3+ Threes', 'point': 2.5, 'odds': 4}],
                'ladder_legs': [{'market': '3+ Threes', 'point': 2.5, 'odds': 4, 'stake': .15}]}]}]
    with patch('prop_hunter_shared_utils.select_pick_rows', return_value=[]), patch('prop_hunter_shared_utils.safe_json_load', return_value=history):
        virtual = select_settlement_picks()
        assert len(virtual) == 1 and virtual[0]['player'] == 'Only Ladder'
        assert virtual[0]['stake'] == .15 and virtual[0]['_source_tables'] == []
    combo = history[0]['kombis'][0]
    assert reporter._leg_rows(combo)[0]['stake'] == .15

    old_pick = {'player': 'Historical Hitter', 'league': 'MLB', 'date': '2026-07-08', 'market': 'Home Run', 'status': 'pending'}
    with patch.object(mlb, 'select_pick_rows', return_value=[old_pick]), patch.dict('os.environ', {'PH_MLB_RESULTS_LOOKBACK_DAYS': '0'}):
        assert mlb.pending_player_groups() == [('Historical Hitter', {'hitting'})]

    raw = {'player': 'Hitter', 'market': 'home_runs Over 0.5', 'line': .5, 'date': '2026-10-22'}
    rows = [{'pick_raw': raw, 'actual_value': 2, 'result': 'win'}]
    indexes = reporter._index_results(rows)
    ladder = {'type': 'ladder', 'date': '2026-10-22', 'ladder_legs': [
        {'player': 'Hitter', 'market': 'Home Run', 'line': .5, 'odds': 3, 'stake': .1},
        {'player': 'Hitter', 'market': 'home_runs Over 1.5', 'line': 1.5, 'odds': 8, 'stake': .1}]}
    assert reporter._settle_combo(ladder, *indexes)
    assert ladder['result'] == 'win' and ladder['profit'] == .9, ladder
    assert not reporter._settle_combo(ladder, *indexes), 'second grading must be idempotent'
    wrong_day = dict(ladder, date='2026-10-23')
    assert not reporter._settle_combo(wrong_day, *indexes)
    one = {'pick_id': 'p', 'result': 'loss', 'settled_at': '2026-10-22'}
    two = dict(one, result='win', settled_at='2026-10-23')
    assert unique_results([one, two]) == [two]
    workflow = Path('.github/workflows/prophunter_results.yml').read_text()
    assert workflow.index('PH_GAMELOG_KEEP_PER_PLAYER=15') > workflow.index('          python prop_hunter_settler_extras.py\n')
    print('SETTLEMENT BACKLOG REGRESSIONS PASSED')


if __name__ == '__main__':
    main()
