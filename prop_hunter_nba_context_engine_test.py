from prop_hunter_nba_context_engine import (shot_observation, shot_form, index_position_defense,
                                            matchup_position_evidence)
base=dict(source="nba_official_shotchart", player_id=123, game_id="0022600001",
          game_event_id=4, game_date="20261115", shot_zone_basic="Above the Break 3",
          shot_attempted_flag=1, shot_made_flag=1)
assert shot_observation(base, nba_player_id=123, season="2026-27",before_date="2026-11-17")
assert not shot_observation(base,nba_player_id=124,season="2026-27",before_date="2026-11-17")
assert not shot_observation(dict(base,game_date="20261117"),nba_player_id=123,season="2026-27",before_date="2026-11-17")
assert not shot_observation(dict(base,source="random_blog"),nba_player_id=123,season="2026-27",before_date="2026-11-17")
assert not shot_observation(dict(base,game_id="fake"),nba_player_id=123,season="2026-27",before_date="2026-11-17")
assert not shot_observation(dict(base,shot_made_flag=2),nba_player_id=123,season="2026-27",before_date="2026-11-17")
events=[base,dict(base,game_event_id=5,shot_made_flag=0),dict(base,game_event_id=5,shot_made_flag=0)]
out=shot_form(events,nba_player_id=123,season="2026-27",before_date="2026-11-17")
assert out["l5"]["games"]==1 and out["l5"]["zones"]["above the break 3"]=={"fga":2,"fgm":1,"fg_pct":0.5}
assert not out["model_ready"]
dvp=dict(source="fantasypros_dvp",opponent_team="BOS",position="PG",stat="assists",
         allowed_per_game=7.2,games=15,season="2026-27",observed_on="2026-11-17")
index=index_position_defense([dvp],as_of="2026-11-17")
assert matchup_position_evidence(index,opponent="BOS",position="PG",stat="assists")["allowed_per_game"]==7.2
assert matchup_position_evidence(index,opponent="BOS",position=None,stat="assists") is None
assert not index_position_defense([dvp,dvp],as_of="2026-11-17")
assert not index_position_defense([dict(dvp,stat="fantasy_points")],as_of="2026-11-17")
print("NBA CONTEXT ENGINE REGRESSION PASSED")
