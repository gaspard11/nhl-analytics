{{ config(materialized='incremental', incremental_strategy='delete+insert', unique_key='game_id') }}

with base as (
  select
    pbp.* exclude (fetched_at),
    lpad(cast(pbp.situation_code as varchar), 4, '0') as sc,
    games.home_team_id,
    games.away_team_id,
    greatest(pbp.fetched_at, games.fetched_at) as fetched_at
  from {{ ref('fct_games') }} games
  join {{ ref('fct_games_events') }} pbp on games.game_id = pbp.game_id
  {% if is_incremental() %}
  where greatest(pbp.fetched_at, games.fetched_at) > (select max(fetched_at) from {{ this }})
  {% endif %}
),

events as (
    select
        game_id,
        sort_order,
        team_id,
        event_id,
        event_type,
        situation,
        home_team_id,
        away_team_id,
        details,
        lpad(to_varchar(situation_code), 4, '0') as sc 
    from base
    where period_descriptor <> 'SO'
      and situation_code is not null
),

s as (
    select
        game_id,
        sort_order,
        home_team_id,
        away_team_id,
        (substr(sc, 3, 1) + substr(sc, 4, 1))
      - (substr(sc, 1, 1) + substr(sc, 2, 1)) as diff
    from events
),

power_play_count as (
    select
        game_id,
        iff(diff > 0, home_team_id, away_team_id) as team_id,
        count(*) as count_pp
    from (select *, lag(diff, 1, 0) over (partition by game_id order by sort_order) as prev_diff from s)
    where diff <> 0
    and (sign(diff) <> sign(prev_diff)          -- a team gains the advantage
        or abs(diff) > abs(prev_diff))         -- or the same team's advantage grows (5v4 -> 5v3)
    group by all
),

power_play_goals as (
    select
        game_id,
        team_id,
        count(event_id) as count_goals
    from events
    where event_type = 'goal' and situation = 'PP'
    group by game_id, team_id
),

power_play_rate as (
    select
        ppc.game_id,
        ppc.team_id,
        coalesce(ppg.count_goals / ppc.count_pp, 0) as pp_rate,
        coalesce(ppg.count_goals, 0) as pp_goals,
        coalesce(ppc.count_pp, 0) as pp_count
    from power_play_count ppc
    left join power_play_goals ppg on ppc.game_id = ppg.game_id and ppc.team_id = ppg.team_id
)


select 
    game_id,
    team_id,
    event_type,
    count(event_id) as count_events
from events
where event_type in ('takeaway', 'giveaway', 'hit', 'shot-on-goal', 'blocked-shot', 'faceoff')
group by game_id, team_id, event_type

union all 

select 
    game_id,
    team_id,
    event_type,
    sum(details:duration::int) as count_events
from events
where event_type = 'penalty'
group by game_id, team_id, event_type

union all

select 
    game_id,
    team_id,
    'pp_rate' as event_type,
    pp_rate as count_events
from power_play_rate

union all

select 
    game_id,
    team_id,
    'pp_goals' as event_type,
    pp_goals as count_events
from power_play_rate

union all

select 
    game_id,
    team_id,
    'pp_count' as event_type,
    pp_count as count_events
from power_play_rate
