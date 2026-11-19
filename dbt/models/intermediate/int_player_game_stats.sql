-- Stats common to skaters and goalies, per game: one row per game, player and stat (long format).
-- A new stat is one more block in the union all. A player with no row for a stat had none of it.
-- Goalie-only stats are in int_goalie_game_stats, skater-only stats in int_skater_game_stats.
-- Season-to-date totals and computed stats (points...) are in the marts fct_skater_stats and
-- fct_goalie_stats.

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

-- Time on ice: the sum of the player's shifts. A player has a row only if they had at least one
-- shift, which is what makes a game played (counted in the marts)
player_tois as (
    select
        game_id,
        player_id,
        sum(split_part(duration, ':', 1)::int * 60 + split_part(duration, ':', 2)::int) as toi_seconds
    from {{ ref('stg_nhl_api__games_shifts') }}
    group by game_id, player_id
),

-- Goals and assists, shootout goals excluded (stg_nhl_api__goals has none)
scoring_events as (

    select game_id, scoring_player_id as player_id, 1 as goals, 0 as assists
    from {{ ref('stg_nhl_api__goals') }}
    where scoring_player_id is not null

    union all

    select game_id, assist1_player_id as player_id, 0 as goals, 1 as assists
    from {{ ref('stg_nhl_api__goals') }}
    where assist1_player_id is not null

    union all

    select game_id, assist2_player_id as player_id, 0 as goals, 1 as assists
    from {{ ref('stg_nhl_api__goals') }}
    where assist2_player_id is not null

),

player_scoring as (
    select
        game_id,
        player_id,
        sum(goals)   as goals,
        sum(assists) as assists
    from scoring_events
    group by game_id, player_id
),

-- TODO penalty_minutes: the `penalty` events of stg_nhl_api__pbp, the penalized player is
-- player_1_id, the length of the penalty is in `details` (minutes). One CTE here, then one block
-- in the union all below.

stats as (

    select game_id, player_id, 'toi_seconds' as stat_name, toi_seconds as stat_value
    from player_tois
    union all
    select game_id, player_id, 'goals', goals
    from player_scoring
    where goals > 0
    union all
    select game_id, player_id, 'assists', assists
    from player_scoring
    where assists > 0
    -- TODO union all: penalty_minutes

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
