-- Optional NBA game-level usage observations, NOT season aggregates.
-- Apply only after live official BoxScoreUsageV3 payload validation.
create table if not exists public.prop_hunter_nba_game_usage (
  nba_player_id bigint not null check (nba_player_id > 0),
  nba_game_id text not null check (nba_game_id ~ '^[0-9]{10}$'),
  game_date date not null,
  usage_pct double precision not null check (usage_pct >= 0 and usage_pct <= 100),
  source text not null default 'nba_official_boxscore_usage_v3'
    check (source = 'nba_official_boxscore_usage_v3'),
  collected_at timestamptz not null default now(),
  primary key (nba_player_id, nba_game_id)
);
create index if not exists prop_hunter_nba_game_usage_player_date_idx
  on public.prop_hunter_nba_game_usage (nba_player_id, game_date desc);
-- No model joins by player name; use NBA ID mapping after verification.
