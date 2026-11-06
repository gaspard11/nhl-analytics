{{
    config(
        materialized='incremental',
        incremental_strategy='delete+insert',
        unique_key='game_id'
    )
}}

with events as (

    select pbp.*
    from {{ ref('fct_games_events') }} as pbp
    {% if is_incremental() %}
    where pbp.fetched_at > (select max(fetched_at) from {{ this }})
    {% endif %}

),

rosters as (

    select r.*
    from {{ ref('fct_game_rosters') }} as r
    {% if is_incremental() %}
    where r.fetched_at > (select max(fetched_at) from {{ this }})
    {% endif %}

),

-- games in this batch, with the fetched_at that every stat row will carry
games as (

    select
        game_id,
        max(fetched_at) as fetched_at
    from events
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
        go.game_id,
        go.team_id,
        count(go.event_id) as pp_goals
    from {{ ref('fct_goals') }} as go
    inner join games as g
        on g.game_id = go.game_id     -- only the games of this batch
    where go.strength_situation = 'PP'
    group by go.game_id, go.team_id

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

),

blocked_shots as (
    select 
        r.game_id,
        r.team_id,
        count(event_id) as blocked_shots,
        max(greatest(e.fetched_at, r.fetched_at)) as fetched_at
    from events e
    join rosters r on e.game_id = r.game_id and player_1_id = r.player_id
    where event_type = 'blocked-shot' and e.team_id <> r.team_id
    group by r.game_id, r.team_id
),

leading_duration as (
    select
        l.game_id,
        l.leading_team_id as team_id,
        sum(l.duration_s) as leading_duration,
        max(g.fetched_at) as fetched_at
    from {{ ref('fct_games_leading_segments') }} as l
    inner join games as g
        on g.game_id = l.game_id      -- only the games of this batch
    where l.leading_team_id > 0
    group by l.game_id, l.leading_team_id
)

select
    game_id,
    team_id,
    CONCAT(UPPER(LEFT(event_type, 1)) || LOWER(SUBSTR(event_type, 2)),'s') as stat_name,
    count(event_id) as stat_value,
    max(fetched_at) as fetched_at
from events
where event_type in (
    'takeaway',
    'giveaway',
    'hit',
    'faceoff'
)
group by game_id, team_id, event_type

union all

select
    game_id,
    team_id,
    'Shots On Goal' as stat_name,
    count(event_id) as stat_value,
    max(fetched_at) as fetched_at
from events
where event_type in (
    'goal',
    'shot-on-goal'
)
group by game_id, team_id

union all

select
    game_id,
    team_id,
    'Penalty Minutes' as stat_name,
    sum(details:duration::int) as stat_value,
    max(fetched_at) as fetched_at
from events
where event_type = 'penalty'
group by game_id, team_id

union all

select
    r.game_id,
    r.team_id,
    'Power Play %' as stat_name,
    r.pp_rate as stat_value,
    g.fetched_at
from pp_rate as r
inner join games as g
    on g.game_id = r.game_id

union all

select
    r.game_id,
    r.team_id,
    'Power Play Goals' as stat_name,
    r.pp_goals as stat_value,
    g.fetched_at
from pp_goals as r
inner join games as g
    on g.game_id = r.game_id


union all

select
    r.game_id,
    r.team_id,
    'Power Play Opportunities' as stat_name,
    r.pp_opportunities as stat_value,
    g.fetched_at
from pp_opp as r
inner join games as g
    on g.game_id = r.game_id

union all 

select 
    game_id,
    team_id,
    'Blocked Shots' as stat_name,
    blocked_shots as stat_value,
    fetched_at
from blocked_shots

union all 

select
    game_id,
    team_id,
    'Leading time',
    leading_duration,
    fetched_at
from leading_duration

