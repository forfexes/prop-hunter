from prop_hunter_season_usage_mapping import map_verified_season_usage
row={"season":"2026-27","player_name":"Test Player","team":"ABC","usage_pct":26.5,"scope":"season","source":"boxscorelab_csv_cc_by_4_0"}
assert map_verified_season_usage([row], {}) == []
assert map_verified_season_usage([row], {("2026-27","Test Player","ABC"):{"nba_player_id":123,"method":"guess"}}) == []
mapped=map_verified_season_usage([row], {("2026-27","Test Player","ABC"):{"nba_player_id":123,"method":"verified_external_id"}})
assert len(mapped)==1 and mapped[0]["nba_player_id"]==123
assert "game_id" not in mapped[0] and "usage_l10" not in mapped[0]
try:
    map_verified_season_usage([row,row], {("2026-27","Test Player","ABC"):{"nba_player_id":123,"method":"verified_external_id"}})
    raise AssertionError("duplicate accepted")
except ValueError:
    pass
print("NBA verified season ID mapping tests passed")
