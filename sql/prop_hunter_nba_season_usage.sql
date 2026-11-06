-- Free NBA season usage observations (BoxScore Lab and audited CSV providers).
-- This table is intentionally separate from official NBA game-level usage.
-- Never use these season rows to populate L5/L10/L15.
create table if not exists public.prop_hunter_nba_season_usage (
  nba_player_id bigint not null check (nba_player_id > 0),
  season text not null check (season ~ '^[0-9]{4}-[0-9]{2}$'),
  usage_pct double precision not null check (usage_pct >= 0 and usage_pct <= 100),
  source text not null check (source in (
    'boxscorelab_csv_cc_by_4_0',
    'basketball_reference_csv',
    'nbastuffer_csv',
    'databallr_csv'
  )),
  source_player_name text not null,
  id_mapping_method text not null check (id_mapping_method = 'verified_external_id'),
  collected_at timestamptz not null default now(),
  primary key (nba_player_id, season, source)
);
create index if not exists prop_hunter_nba_season_usage_season_idx
  on public.prop_hunter_nba_season_usage (season, source);
-- Raw BoxScore Lab CSV has player names, not canonical NBA IDs.
-- Keep unmapped rows out of this table until a verified external ID mapping exists.
-- Never enable write permissions for anon/authenticated roles.
