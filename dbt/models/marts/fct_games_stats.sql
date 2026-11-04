{{
    config(
        materialized='incremental',
        incremental_strategy='delete+insert',
        unique_key='game_id'
    )
}}

with base as (

    select pbp.*
    from {{ ref('fct_games_events') }} as pbp
    {% if is_incremental() %}
    where pbp.fetched_at > (select max(fetched_at) from {{ this }})
    {% endif %}

),

-- games in this batch, with the fetched_at that every stat row will carry
games as (

    select
        game_id,
        max(fetched_at) as fetched_at
    from base
    group by game_id

),

pp_opp as (

    select
        s.game_id,
        s.pp_team_id as team_id,
        sum(s.pp_opportunities) as pp_opportunities
    from {{ ref('fct_games_pp_segments') }} as s
    inner join games as g
        on g.game_id = s.game_id      -- only the games of this batch
    where s.pp_team_id is not null    -- even-strength segments have no PP team
    group by s.game_id, s.pp_team_id

),

pp_goals as (

    select
        game_id,
        team_id,
        count(event_id) as pp_goals
    from base
    where event_type = 'goal'
      and situation = 'PP'
    group by game_id, team_id

),

pp_rate as (

    select
        coalesce(ppo.game_id, ppg.game_id) as game_id,
        coalesce(ppo.team_id, ppg.team_id) as team_id,
        div0(coalesce(ppg.pp_goals, 0), ppo.pp_opportunities) as pp_rate
    from pp_opp as ppo
    full outer join pp_goals as ppg
        on ppo.game_id = ppg.game_id
       and ppo.team_id = ppg.team_id

)

select
    game_id,
    team_id,
    event_type as stat,
    count(event_id) as count_events,
    max(fetched_at) as fetched_at
from base
where event_type in (
    'takeaway',
    'giveaway',
    'hit',
    'shot-on-goal',
    'blocked-shot',
    'faceoff'
)
group by game_id, team_id, event_type

union all

select
    game_id,
    team_id,
    'penalty minutes' as stat,
    sum(details:duration::int) as count_events,
    max(fetched_at) as fetched_at
from base
where event_type = 'penalty'
group by game_id, team_id

union all

select
    r.game_id,
    r.team_id,
    'pp_rate' as stat,
    r.pp_rate as count_events,
    g.fetched_at
from pp_rate as r
inner join games as g
    on g.game_id = r.game_id

union all

select
    r.game_id,
    r.team_id,
    'pp_goals' as stat,
    r.pp_goals as count_events,
    g.fetched_at
from pp_goals as r
inner join games as g
    on g.game_id = r.game_id


union all

select
    r.game_id,
    r.team_id,
    'pp_opp' as stat,
    r.pp_opportunities as count_events,
    g.fetched_at
from pp_opp as r
inner join games as g
    on g.game_id = r.game_id