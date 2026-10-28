#!/usr/bin/env python3
"""Offline coverage for official US gamedays and observed basketball rows."""
from unittest.mock import patch
from prop_hunter_basketball_boxscore import official_gameday, observed_stats, unobserved_log
from prop_hunter_settler import find_gamelog, build_log_index
import prophunter_results as reporter
from prop_hunter_learning_update import learn_builder_correlations
import prop_hunter_results_nba as nba
import prop_hunter_results_wnba as wnba


def main():
    assert official_gameday('2026-08-12T02:00Z') == '2026-08-11'
    assert official_gameday('2026-12-12T02:00:00+00:00') == '2026-12-11'
    assert official_gameday('2026-08-11T18:00Z') == '2026-08-11'
    assert official_gameday('2026-08-11') == '2026-08-11'
    assert official_gameday('2026-08-12T02:00:00') is None
    labels = ['MIN', 'PTS', 'REB', 'AST', '3PT', 'STL', 'BLK', 'TO']
    played = {'athlete': {'displayName': 'Observed Player'}, 'didNotPlay': False,
              'stats': ['27', '11', '7', '2', '2-4', '3', '3', '1']}
    dnp = {'athlete': {'displayName': 'DNP Player'}, 'didNotPlay': True, 'stats': []}
    absent = {'athlete': {'displayName': 'Missing Player'}, 'stats': []}
    payload = {'header': {'competitions': [{'date': '2026-08-12T02:00Z'}]},
               'boxscore': {'players': [{'team': {'displayName': 'A'},
                  'statistics': [{'labels': labels, 'athletes': [played, dnp, absent]}]}]}}
    with patch.object(wnba, 'http_json', return_value=payload):
        wr = wnba.espn_summary_players('official-id', [])
    with patch.object(nba, '_espn_game_payload', return_value=(payload, 'espn_summary')):
        nr = nba.espn_summary_players('official-id', [])
    for rows in (wr, nr):
        assert len(rows) == 1, rows
        r = rows[0]
        assert r['game_date'] == '2026-08-11' and r['pra'] == 20
        assert r['points'] == 11 and r['rebounds'] == 7 and r['threes_made'] == 2
        assert r['raw']['start_time_utc'] == '2026-08-12T02:00Z'
    assert observed_stats({'labels': labels}, dnp) is None
    assert observed_stats({'labels': []}, played) is None
    zero = observed_stats({'labels': labels}, dict(played, stats=['1','0','0','0','0-0','0','0','0']))
    assert zero['points'] == 0 and zero['double_double'] is False
    partial = observed_stats({'labels': ['PTS','AST']}, dict(played, stats=['23','5']))
    assert partial['rebounds'] is None and partial['pra'] is None and partial['double_double'] is None
    five_cat = observed_stats({'labels': labels}, dict(played, stats=['25','5','2','10','0-0','10','0','0']))
    assert five_cat['double_double'] is True
    empty = {'player_name': 'Observed Player', 'league': 'WNBA', 'game_id': 'bad',
             'game_date': '2026-08-11', 'source': 'espn_summary_backfill', 'raw': {'stat_map': {}}, 'points': 0}
    assert unobserved_log(empty)
    pick = {'date': '2026-08-11', 'player': 'Observed Player', 'market': 'points Over 10.5', 'line': 10.5,
            'dedup_key': 'fixture', 'result': 'loss', 'actual_value': 0, 'profit': -.2}
    indexes = reporter._index_results([{'result': 'no_result', 'actual_value': None, 'pick_raw': dict(pick), 'result_raw': empty}])
    withdrawn = reporter._match_result(pick, *indexes)
    assert withdrawn['result'] == 'withdrawn'
    assert reporter._merge_single(pick, withdrawn) and pick['result'] == 'pending'
    assert not reporter._merge_single(pick, withdrawn)
    combo = {'type': 'ladder', 'date': '2026-08-11', 'result': 'loss', 'profit': -.2,
             'leg_details': [dict(pick, stake=.2, odds=2)]}
    assert reporter._settle_combo(combo, *indexes) and combo['result'] == 'pending'
    assert reporter._match_actual_stat(pick, indexes[1]) is None
    combo['builder_profile'] = 'safe'
    combo['leg_details'] = [{'player': 'A', 'market': 'points', 'sport': 'NBA', 'result': 'loss', 'probability': .6},
                            {'player': 'B', 'market': 'rebounds', 'sport': 'NBA', 'result': 'win', 'probability': .7}]
    learned = learn_builder_correlations([{'kombis': [combo]}])
    assert learned['pairs'] == {} and learned['profiles'] == {}, learned
    assert find_gamelog({'player': 'Observed Player', 'date': '2026-08-11', 'league': 'WNBA'}, [empty], {}, build_log_index([empty])) is None
    print('BASKETBALL OFFICIAL DATE / OBSERVED BOXSCORE TEST PASSED')


if __name__ == '__main__':
    main()
