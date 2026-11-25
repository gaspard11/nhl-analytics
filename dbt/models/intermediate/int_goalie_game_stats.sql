-- Goalie-only stats, per game: one row per game, goalie and stat (long format). A new stat is one
-- more block in the union all. A goalie with no row for a stat had none of it.
-- Stats common to every player (games played, time on ice, goals, assists) are in
-- int_player_game_stats. Season-to-date totals and computed stats (GAA, save %) are in fct_goalie_stats.

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

-- The goalies who played each game (at least one shift), with how many goalies their team used:
-- a shutout only goes to a goalie who played the whole game alone
goalies_played as (
    select
        s.game_id,
        s.player_id,
        s.team_id,
        count(distinct s.player_id) over (partition by s.game_id, s.team_id) as c_goalies
    from {{ ref('stg_nhl_api__games_shifts') }} s
    join {{ ref('dim_players') }} p on s.player_id = p.player_id
    where p.position = 'G'
    group by s.game_id, s.player_id, s.team_id
),

shutouts_awarded_games as (
    select
        g.game_id,
        g.player_id
    from goalies_played g
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

games_started as (
    select distinct
        game_id,
        s.player_id
    from {{ ref('stg_nhl_api__games_shifts') }} s
    join {{ ref('dim_players') }} p
    on s.player_id = p.player_id
    where p.position = 'G' and s.start_time = '00:00' and s.period = 1
),

decisive_goals as (
    select
        gs.game_id,
        gs.event_id,
        gs.team_id,
        gs.period_number,
        split_part(gs.time_in_period, ':', 1)::int * 60 + split_part(gs.time_in_period, ':', 2)::int as time_in_period_seconds
    from {{ ref('int_goals_situations') }} gs
    where gs.is_game_winning_goal
),

decisive_moments as (
    select
        game_id,
        period_number as decisive_period,
        time_in_period_seconds as decisive_time_seconds,
    from decisive_goals
    union all
    select
        game_id,
        4 as decisive_period,
        300 as decisive_time_seconds
    from {{ ref('int_team_game_results') }}
    where last_period_type = 'SO' and result = 'W'
),

goalie_shifts as (
    select
        game_id,
        s.player_id,
        s.team_id,
        s.period,
        split_part(start_time, ':', 1)::int * 60 + split_part(start_time, ':', 2)::int as start_s
    from {{ ref('stg_nhl_api__games_shifts') }} s
    join {{ ref('dim_players') }} p
    on s.player_id = p.player_id
    where p.position = 'G'
),

decisive_goalie_stat as (
    select
        s.game_id,
        s.player_id,
        gr.result
    from goalie_shifts s
    join decisive_moments d 
    on s.game_id  = d.game_id
    and (
        s.period < d.decisive_period
        or (s.period = d.decisive_period and s.start_s < d.decisive_time_seconds)
    )
    join {{ ref('int_team_game_results') }} gr on s.team_id = gr.team_id and d.game_id = gr.game_id
    qualify row_number() over (partition by s.game_id, s.team_id order by s.period desc, s.start_s desc) = 1
),

stats as (

    select game_id, player_id, 'saves' as stat_name, count_saves as stat_value
    from saves_per_game
    union all
    select game_id, player_id, 'goals_against', count_goals_against
    from goal_against_per_game
    union all
    select game_id, player_id, 'shutout', 1
    from shutouts_awarded_games
    union all
    select game_id, player_id, 'games_started', 1
    from games_started
    union all
    select game_id, player_id, 'awarded_wins', 1
    from decisive_goalie_stat
    where result = 'W'
    union all
    select game_id, player_id, 'awarded_losses', 1
    from decisive_goalie_stat
    where result = 'L'
    union all
    select game_id, player_id, 'awarded_ot_losses', 1
    from decisive_goalie_stat
    where result = 'OT'
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
