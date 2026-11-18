

with game_fetched_at as (
    select
        games.game_id,
        -- latest load of the game's three sources: a reload of any of them recalculates the game
        greatest(
            games.fetched_at,
            pbp.fetched_at,
            coalesce(shifts.fetched_at, games.fetched_at)
        ) as fetched_at
    from {{ ref('stg_nhl_api__games') }} games
    join (select distinct game_id, fetched_at from {{ ref('stg_nhl_api__pbp') }}) pbp
        on pbp.game_id = games.game_id
    left join (select distinct game_id, fetched_at from {{ ref('stg_nhl_api__games_shifts') }}) shifts
        on shifts.game_id = games.game_id
),

goalie_shifts as (
    select
        s.game_id,
        s.player_id,
        s.team_id,
        split_part(s.duration, ':', 1)::int * 60 + split_part(s.duration, ':', 2)::int as duration_seconds
    from {{ ref('stg_nhl_api__games_shifts') }} s
    join {{ ref('dim_players') }} p on s.player_id = p.player_id
    where p.position = 'G'
),

goalie_tois as (
    select
        game_id,
        player_id,
        team_id,
        sum(duration_seconds) as toi_seconds,
        COUNT(distinct player_id) over (partition by game_id, team_id) as c_goalies
    from goalie_shifts
    group by team_id, game_id, player_id
),

shutouts_awarded_games as (
    select
        g.game_id,
        player_id
    from goalie_tois g
    join {{ ref('int_team_game_results') }} ga on g.team_id = ga.team_id and g.game_id = ga.game_id
    where c_goalies = 1
    and (
        ga.goals_against = 0
        or (ga.last_period_type = 'SO' and ga.goals_for = 0)
    )
    ),


goal_against_per_game as (
    select
        game_id,
        goalie_in_net_id as player_id,
        COUNT(event_id) as count_goals_against
    from {{ ref('stg_nhl_api__pbp') }}
    where event_type = 'goal' and period_number <> 5 and goalie_in_net_id is not null
    group by game_id, goalie_in_net_id
),

saves_per_game as (
    select
        game_id,
        goalie_in_net_id as player_id,
        COUNT(event_id) as count_saves
    from {{ ref('stg_nhl_api__pbp') }}
    where event_type = 'shot-on-goal' and period_number <> 5 and goalie_in_net_id is not null
    group by game_id, goalie_in_net_id
),

stats as (

    select game_id, player_id, 'toi_seconds' as stat_name, toi_seconds as stat_value
    from goalie_tois
    union all
    select game_id, player_id, 'saves', count_saves
    from saves_per_game
    union all
    select game_id, player_id, 'goals_against', count_goals_against
    from goal_against_per_game
    union all
    select game_id, player_id, 'shutout', 1
    from shutouts_awarded_games

)

select
    stats.game_id,
    stats.player_id,
    stats.stat_name,
    stats.stat_value,
    f.fetched_at
from stats
join game_fetched_at f
    on f.game_id = stats.game_id