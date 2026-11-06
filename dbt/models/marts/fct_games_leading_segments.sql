{{ config(materialized='incremental', incremental_strategy='delete+insert', unique_key='game_id') }}


with goals as (
    select 
        *
    from {{ ref('fct_goals') }}
    {% if is_incremental() %}
    where fetched_at > (select max(fetched_at) from {{ this }})
    {% endif %}
),
games as (
    select
        *
    from {{ ref('fct_games') }}
    {% if is_incremental() %}
    where fetched_at > (select max(fetched_at) from {{ this }})
    {% endif %}
),

goals_cleaned as (
    select 
        go.game_id,
        home_score,
        away_score,
        case when home_score > away_score then 'home_leads'
        when away_score > home_score then 'away_leads'
        else 'tied' end as leading_team_after,
        case when home_score > away_score then home_team_id
        when away_score > home_score then away_team_id
        else 0 end as leading_team_id_after,
        (period_number - 1) * 1200
        + split_part(time_in_period, ':', 1)::int * 60
        + split_part(time_in_period, ':', 2)::int as time_game_seconds,
        ga.fetched_at
    from goals go
    join games ga on go.game_id = ga.game_id
),

last_event_per_game as (
    select
        game_id,
        home_score,
        away_score,
        leading_team_after,
        leading_team_id_after,
        case when time_game_seconds > 3600 then time_game_seconds
        else 3600 end as time_game_seconds,
        fetched_at
    from goals_cleaned
    qualify row_number() over (
        partition by game_id
        order by time_game_seconds desc
    ) = 1
),

all_events_cleaned as (
    select 
        * 
    from goals_cleaned
    union all
    select
        game_id,
        0,
        0,
        'tied' as leading_team_after,
        0 as leading_team_id_after,
        0,
        fetched_at
    from games
    union all
    select
        *
    from last_event_per_game
),

ordered as (
    select
        game_id,
        leading_team_after    as state,
        leading_team_id_after as leading_team_id,
        time_game_seconds     as start_s,
        fetched_at,
        lead(time_game_seconds) over (partition by game_id order by time_game_seconds) as end_s,
        lag(leading_team_after) over (partition by game_id order by time_game_seconds) as prev_state
    from all_events_cleaned
),

flagged as (
    select
        *,
        sum(case when prev_state = state then 0 else 1 end)
            over (partition by game_id order by start_s
                  rows between unbounded preceding and current row) as seg_id
    from ordered
)
select
    game_id,
    state,
    leading_team_id,
    min(start_s)              as start_s,
    max(end_s)                as end_s,
    max(end_s) - min(start_s) as duration_s,
    max(fetched_at)           as fetched_at
from flagged
where end_s is not null
group by game_id, seg_id, state, leading_team_id
order by game_id, start_s