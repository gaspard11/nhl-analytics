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

-- TODO games_started: the goalie in net at the start of the game (their first shift starts at
-- 00:00 of period 1). One CTE here, then one block in the union all below.

-- TODO wins_awarded, losses_awarded, ot_awarded: the decision goes to the goalie in net when the
-- winning team scored the goal that put it ahead for good (goalie_in_net_id of the opponent's
-- goals in stg_nhl_api__pbp, the result in int_team_game_results). One CTE per decision or one CTE
-- with the three, then their blocks in the union all below.

stats as (

    select game_id, player_id, 'saves' as stat_name, count_saves as stat_value
    from saves_per_game
    union all
    select game_id, player_id, 'goals_against', count_goals_against
    from goal_against_per_game
    union all
    select game_id, player_id, 'shutout', 1
    from shutouts_awarded_games
    -- TODO union all: games_started, wins_awarded, losses_awarded, ot_awarded

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
