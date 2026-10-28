#!/usr/bin/env python3
"""Offline regressions for historical debt, source mirroring and ladder grading."""
from unittest.mock import patch, MagicMock
from pathlib import Path
from datetime import datetime, timezone
from prop_hunter_settler import detect_stat, stat_value, result_for_value, persist_settlements
from prop_hunter_shared_utils import _normalise_pick_row, select_settlement_picks, inherit_leg_context
import prop_hunter_results_mlb as mlb
import prophunter_results as reporter
from prop_hunter_learning_update import unique_results
from prop_hunter_pending_audit import classify


def main():
    first_page = MagicMock(status_code=200)
    first_page.json.return_value = [{'result_id': str(i)} for i in range(1000)]
    last_page = MagicMock(status_code=200)
    last_page.json.return_value = [{'result_id': '1000'}, {'result_id': '1001'}]
    with patch.object(reporter, 'SUPABASE_URL', 'https://fixture.invalid'), patch.object(reporter, 'SUPABASE_KEY', 'fixture'), patch.object(reporter.requests, 'get', side_effect=[first_page, last_page]) as get:
        assert len(reporter._fetch_results()) == 1002
        assert [call.kwargs['params']['offset'] for call in get.call_args_list] == ['0', '1000']
    quote = {'date': '2026-10-22', 'player': 'P', 'game': 'A @ B', 'commence_time': '2026-10-23T01:30:00Z'}
    duplicate_quote = dict(quote, market='Different threshold')
    leg = inherit_leg_context({'date': '2026-10-22', 'player': 'P', 'game': 'A @ B'}, [quote, duplicate_quote])
    assert leg['commence_time'] == quote['commence_time']
    teammate = dict(quote, player='Teammate', commence_time='2026-10-23T01:40:00Z')
    assert inherit_leg_context({'date': '2026-10-22', 'player': 'P', 'game': 'A @ B'}, [quote, duplicate_quote, teammate])['commence_time'] == quote['commence_time']
    ambiguous = dict(quote, commence_time='2026-10-23T07:30:00Z')
    assert 'commence_time' not in inherit_leg_context({'date': '2026-10-22', 'player': 'P', 'game': 'A @ B'}, [quote, ambiguous])
    wrong_player_game = dict(quote, game='C @ D', commence_time='2026-10-23T07:30:00Z')
    assert inherit_leg_context({'date': '2026-10-22', 'player': 'P', 'game': 'A @ B'}, [wrong_player_game, teammate])['commence_time'] == teammate['commence_time']
    different_game = dict(quote, game='C @ D', commence_time='2026-10-23T07:30:00Z')
    assert inherit_leg_context({'date': '2026-10-22', 'player': 'P', 'game': 'A @ B'}, [quote, different_game])['commence_time'] == quote['commence_time']
    today = datetime.now(timezone.utc).date().isoformat()
    from prop_hunter_settler import _pick_ready_for_settlement
    assert not _pick_ready_for_settlement({'date': today})
    assert not reporter._settlement_ready_time({'date': today})
    early = {'date': today, 'result': 'pending'}
    assert not reporter._merge_single(early, {'result': 'win', 'actual_value': 0})
    assert early['result'] == 'pending'
    combo = {'type': 'ladder', 'date': today, 'result': 'win', 'profit': 2,
             'leg_details': [{'player': 'P', 'market': 'points', 'line': 10.5, 'odds': 2, 'stake': .1}]}
    assert reporter._settle_combo(combo, {}, {})
    assert combo['result'] == 'pending' and combo['profit'] is None
    card = {'text': 'Original tip', 'settlement_text': 'Old premature win', 'pick_keys': ['p']}
    text = reporter._decorate_card(card, [{'dedup_key': 'p', 'result': 'pending'}], [])
    assert text and '1⏳' in text and 'Old premature win' not in text
    assert reporter._index_results([{'result': 'win', 'pick_raw': {'date': today}}]) == ({}, {})
    for market, expected in [('pa Over 18.5','pa'), ('PR Under 19.5','pr'),
                             ('passing_yards Over 200.5','passing_yards'), ('Pass Yds Over 229.5','passing_yards'),
                             ('Rebs+Asts Over 9.5','ra'), ('Rebounds+Assists Over 9.5','ra'),
                             ('Pts+Rebs+Asts Over 19.5','pra'), ('Pts+Rebs Over 14.5','pr'), ('total_saves Over 20.5','goalie_saves'),
                             ('Home Run','home_runs'), ('3-PT Made Over 1.5','threes_made')]:
        assert detect_stat(market) == expected, market
    assert detect_stat('Hits+Runs+RBIS Under 0.5') == 'hits_runs_rbis'
    assert stat_value({'hits': 1, 'runs': 2, 'rbi': 3}, 'hits_runs_rbis') == 6
    assert detect_stat('Hits Over 1.5 Over 0.5') is None
    assert classify({'market': 'Hits Over 1.5 Over 0.5'}, [], {}) == 'ambiguous_market_line'
    assert classify({'market': 'Season Receiving Yards Over 649.5'}, [], {}) == 'unsupported_season_or_fantasy_market'
    assert classify({'league': 'NBA/WNBA', 'market': 'points'}, [], {}) == 'ambiguous_league'
    assert detect_stat('Season Receiving Yards Over 649.5') is None
    assert detect_stat('Fantasy Points Over 8.5') is None
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

    with patch.object(mlb, 'http_json', return_value={'people': [{'id': 66, 'fullName': 'Teoscar Hernández'}]}):
        assert mlb.find_player('Teoscar Hernandez')['id'] == 66

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
