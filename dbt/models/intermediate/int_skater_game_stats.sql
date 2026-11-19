-- Skater-only stats, per game: one row per game, skater and stat (long format), like
-- int_player_game_stats and int_goalie_game_stats. A new stat is one more block in the union all.
-- Season-to-date totals are in fct_skater_stats.
--
-- then join this model in fct_skater_stats (see the TODO there).


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

shots_per_game as (
    select 
        game_id,
        player_1_id as player_id,
        count(*) as shots
    from {{ ref('stg_nhl_api__pbp') }}
    where event_type in('shot-on-goal','goal') and player_1_id is not null and period_number <> 5
    group by game_id, player_1_id
),

goal_events as (
    select game_id, scoring_player_id as player_id, 'goal' as role, strength_situation
    from {{ ref('int_goals_situations') }}
    where scoring_player_id is not null

    union all

    select game_id, assist1_player_id as player_id, 'assist' as role, strength_situation
    from {{ ref('int_goals_situations') }}
    where assist1_player_id is not null

    union all

    select game_id, assist2_player_id as player_id, 'assist' as role, strength_situation
    from {{ ref('int_goals_situations') }}
    where assist2_player_id is not null

),

goal_splits as (

    select
        game_id,
        player_id,
        sum(iff(role = 'goal'   and strength_situation = 'EV', 1, 0)) as ev_goals,
        sum(iff(role = 'assist' and strength_situation = 'EV', 1, 0)) as ev_assists,
        sum(iff(role = 'goal'   and strength_situation = 'PP', 1, 0)) as pp_goals,
        sum(iff(role = 'assist' and strength_situation = 'PP', 1, 0)) as pp_assists,
        sum(iff(role = 'goal'   and strength_situation = 'SH', 1, 0)) as sh_goals,
        sum(iff(role = 'assist' and strength_situation = 'SH', 1, 0)) as sh_assists,
        sum(iff(role = 'goal'   and strength_situation = 'PS', 1, 0)) as ps_goals
    from goal_events
    group by game_id, player_id

),

plus_minus_goals as (
    select
        game_id,
        event_id,
        team_id as scoring_team_id,
        period_number,
        split_part(time_in_period, ':', 1)::int * 60 + split_part(time_in_period, ':', 2)::int as goal_s
    from {{ ref('int_goals_situations') }}
    where strength_situation in ('SH', 'EV')
),

skater_shifts as (
    select 
        game_id,
        s.team_id,
        s.player_id,
        period,
        split_part(start_time, ':', 1)::int * 60 + split_part(start_time, ':', 2)::int as start_s,
        split_part(end_time, ':', 1)::int * 60 + split_part(end_time, ':', 2)::int as end_s,
    from {{ ref('stg_nhl_api__games_shifts') }} s
    join {{ ref('dim_players') }} p on s.player_id = p.player_id
    where p.position <> 'G'
),

plus_minus_per_game as (
    select 
        s.game_id,
        s.player_id,
        sum(iff(s.team_id = g.scoring_team_id, 1, -1)) as plus_minus
    from skater_shifts s 
    join plus_minus_goals g 
    on s.game_id = g.game_id
    and s.period = g.period_number
    and s.start_s < g.goal_s
    and s.end_s >= g.goal_s
    group by s.game_id, s.player_id
),

-- TODO plus_minus: +1 for every skater on the ice for an even strength or short handed goal of
-- their team, -1 for the other team's skaters; power play goals and penalty shots don't count.
-- Who was on the ice: the shifts (stg_nhl_api__games_shifts) that cover the time of the goal.

stats as (
    select game_id, player_id, 'shots' as stat_name, shots as stat_value
    from shots_per_game where shots > 0
    union all
    select game_id, player_id, 'ev_goals' as stat_name, ev_goals as stat_value
    from goal_splits where ev_goals > 0
    union all
    select game_id, player_id, 'ev_assists' as stat_name, ev_assists as stat_value
    from goal_splits where ev_assists > 0
    union all
    select game_id, player_id, 'pp_goals' as stat_name, pp_goals as stat_value
    from goal_splits where pp_goals > 0
    union all
    select game_id, player_id, 'pp_assists' as stat_name, pp_assists as stat_value
    from goal_splits where pp_assists > 0
    union all
    select game_id, player_id, 'sh_goals' as stat_name, sh_goals as stat_value
    from goal_splits where sh_goals > 0
    union all
    select game_id, player_id, 'sh_assists' as stat_name, sh_assists as stat_value
    from goal_splits where sh_assists > 0
    union all
    select game_id, player_id, 'ps_goals' as stat_name, ps_goals as stat_value
    from goal_splits where ps_goals > 0
    union all
    select game_id, player_id, 'plus_minus', plus_minus
    from plus_minus_per_game
    where plus_minus <> 0
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
