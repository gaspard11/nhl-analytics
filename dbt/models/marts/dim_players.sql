{{ config(materialized='incremental', unique_key='player_id', incremental_strategy='merge') }}

-- One row per player who has recorded a point, with the team of their most recent game with a point.

with goal_events as (

    select
        goals.scoring_player_id,
        goals.assist1_player_id,
        goals.assist2_player_id,
        goals.team_id,
        games.game_date,
        greatest(goals.fetched_at, games.fetched_at) as fetched_at
    from {{ ref('stg_nhl_api__goals') }} goals
    join {{ ref('stg_nhl_api__games') }} games
        on games.game_id = goals.game_id
    {% if is_incremental() %}
    where greatest(goals.fetched_at, games.fetched_at) > (select max(fetched_at) from {{ this }})
    {% endif %}

),

player_teams as (

    select scoring_player_id as player_id, team_id, game_date, fetched_at
    from goal_events
    where scoring_player_id is not null

    union all

    select assist1_player_id as player_id, team_id, game_date, fetched_at
    from goal_events
    where assist1_player_id is not null

    union all

    select assist2_player_id as player_id, team_id, game_date, fetched_at
    from goal_events
    where assist2_player_id is not null

),

current_teams as (

    select *
    from player_teams
    qualify row_number() over (partition by player_id order by game_date desc) = 1

),

players as (

    select * from {{ ref('stg_nhl_api__players') }}

)

select
    players.player_id,
    players.first_name,
    players.last_name,
    players.position,
    current_teams.team_id,
    players.headshot_url,
    current_teams.fetched_at
from players
join current_teams
    on current_teams.player_id = players.player_id
