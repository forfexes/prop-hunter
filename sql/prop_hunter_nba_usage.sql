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

-- Read-only form projection from observed official NBA game usage.
create or replace view public.prop_hunter_nba_usage_form as
with ranked as (
  select nba_player_id, nba_game_id, game_date, usage_pct,
         row_number() over (partition by nba_player_id
                            order by game_date desc, nba_game_id desc) as rn
  from public.prop_hunter_nba_game_usage
)
select nba_player_id,
       count(*) filter (where rn <= 5) as l5_observed,
       case when count(*) filter (where rn <= 5) = 5
            then round(avg(usage_pct) filter (where rn <= 5)::numeric, 4) end as usage_l5,
       count(*) filter (where rn <= 10) as l10_observed,
       case when count(*) filter (where rn <= 10) = 10
            then round(avg(usage_pct) filter (where rn <= 10)::numeric, 4) end as usage_l10,
       count(*) filter (where rn <= 15) as l15_observed,
       case when count(*) filter (where rn <= 15) = 15
            then round(avg(usage_pct) filter (where rn <= 15)::numeric, 4) end as usage_l15
from ranked where rn <= 15 group by nba_player_id;
