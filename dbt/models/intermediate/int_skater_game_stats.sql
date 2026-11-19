-- Skater-only stats, per game: one row per game, skater and stat (long format), like
-- int_player_game_stats and int_goalie_game_stats. A new stat is one more block in the union all.
-- Season-to-date totals are in fct_skater_stats.
--
-- Template, disabled until its first stat is written: remove the config line below, write the stat,
-- then join this model in fct_skater_stats (see the TODO there).

{{ config(enabled=false) }}

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

-- TODO shots: shots on goal of the player, the `shot-on-goal` and `goal` events of
-- stg_nhl_api__pbp (player_1_id), shootout excluded (period_number <> 5).

-- TODO ev_goals, ev_assists, pp_goals, pp_assists, sh_goals, sh_assists: the goals of fct_goals
-- split by strength_situation (EV, PP, SH; PS = penalty shot, decide where it goes), for the scorer
-- and the two assists.

-- TODO plus_minus: +1 for every skater on the ice for an even strength or short handed goal of
-- their team, -1 for the other team's skaters; power play goals and penalty shots don't count.
-- Who was on the ice: the shifts (stg_nhl_api__games_shifts) that cover the time of the goal.

stats as (

    -- TODO one block per stat, e.g.
    -- select game_id, player_id, 'shots' as stat_name, shots as stat_value
    -- from shots_per_game
    -- union all
    -- ...

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
