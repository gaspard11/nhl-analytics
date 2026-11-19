{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['season', 'ranking_date'],
    on_schema_change='fail'
) }}

-- Season-to-date stats per skater, for every game date, from the skater's first game of the season.
-- The running totals are kept here (cumulative, incremental); the per-game stats come from
-- int_player_game_stats (stats common to every player) and, once it exists, int_skater_game_stats.
-- Computed stats (points) are computed on each row from the totals.
-- No ranking: the app sorts on the stat it shows.

with games as (

    select
        game_id,
        season,
        game_date
    from {{ ref('stg_nhl_api__games') }}

),

skaters as (

    select player_id
    from {{ ref('dim_players') }}
    where position <> 'G'

),

-- Every per-game stat of the skaters, long format
game_stats as (

    select game_id, player_id, stat_name, stat_value, fetched_at
    from {{ ref('int_player_game_stats') }}

    -- TODO once int_skater_game_stats is enabled, add the same select from ref('int_skater_game_stats')
    -- with a union all (written with the double curly braces: Jinja runs even inside SQL comments,
    -- so they can't be written here while the model is disabled)

),

-- One row per skater per game date, one column per stat. A player plays at most one game a day
skater_games as (

    select
        g.season,
        g.game_date,
        s.player_id,
        sum(iff(s.stat_name = 'toi_seconds', 1, 0))              as games_played,
        sum(iff(s.stat_name = 'toi_seconds', s.stat_value, 0))   as toi_seconds,
        sum(iff(s.stat_name = 'goals', s.stat_value, 0))         as goals,
        sum(iff(s.stat_name = 'assists', s.stat_value, 0))       as assists,
        -- TODO one line per new stat, e.g. sum(iff(s.stat_name = 'penalty_minutes', s.stat_value, 0)) as penalty_minutes,
        max(s.fetched_at)                                        as fetched_at
    from game_stats s
    join games g
        on g.game_id = s.game_id
    join skaters k
        on k.player_id = s.player_id
    group by g.season, g.game_date, s.player_id

),

-- 1. Batch start: earliest game date among games loaded since the last run, per season
batch_start as (

    select
        season,
        min(game_date) as from_date
    from skater_games
    {% if is_incremental() %}
    where fetched_at > (
        select coalesce(max(_source_fetched_at), '1900-01-01'::timestamp) from {{ this }}
    )
    {% endif %}
    group by season

),

{% if is_incremental() %}
-- 2a. Each skater's last row strictly BEFORE the batch
prior_rows as (

    select
        t.season,
        t.player_id,
        t.games_played,
        t.toi_seconds,
        t.goals,
        t.assists
        -- TODO one line per new stat: t.<stat>
    from {{ this }} t
    join batch_start b
        on t.season = b.season
       and t.ranking_date < b.from_date
    qualify row_number() over (
        partition by t.season, t.player_id
        order by t.ranking_date desc
    ) = 1

),
{% endif %}

-- 2b. Skaters to compute: those with a row before the batch + those who play during the batch
batch_players as (

    {% if is_incremental() %}
    select season, player_id
    from prior_rows

    union
    {% endif %}

    select distinct
        e.season,
        e.player_id
    from skater_games e
    join batch_start b
        on e.season = b.season
       and e.game_date >= b.from_date

),

-- 2c. Every skater gets a starting point (0 when nothing was found)
prior_state as (

    select
        bp.season,
        bp.player_id,
        {% if is_incremental() %}
        coalesce(p.games_played, 0)  as prior_games_played,
        coalesce(p.toi_seconds, 0)   as prior_toi_seconds,
        coalesce(p.goals, 0)         as prior_goals,
        coalesce(p.assists, 0)       as prior_assists
        -- TODO one line per new stat: coalesce(p.<stat>, 0) as prior_<stat>
        {% else %}
        0                            as prior_games_played,
        0                            as prior_toi_seconds,
        0                            as prior_goals,
        0                            as prior_assists
        -- TODO one line per new stat: 0 as prior_<stat>
        {% endif %}
    from batch_players bp
    {% if is_incremental() %}
    left join prior_rows p
        on p.season = bp.season
       and p.player_id = bp.player_id
    {% endif %}

),

-- 3. Days to (re)compute: every game date from the batch start onwards
batch_dates as (

    select distinct
        g.season,
        g.game_date as ranking_date
    from games g
    join batch_start b
        on g.season = b.season
       and g.game_date >= b.from_date

),

-- 4. New rows = starting point + running total of the daily stats
cumulative as (

    select
        d.season,
        d.ranking_date,
        ps.player_id,

        ps.prior_games_played + sum(coalesce(sg.games_played, 0)) over (
            partition by d.season, ps.player_id order by d.ranking_date
            rows between unbounded preceding and current row
        ) as games_played,

        ps.prior_toi_seconds + sum(coalesce(sg.toi_seconds, 0)) over (
            partition by d.season, ps.player_id order by d.ranking_date
            rows between unbounded preceding and current row
        ) as toi_seconds,

        ps.prior_goals + sum(coalesce(sg.goals, 0)) over (
            partition by d.season, ps.player_id order by d.ranking_date
            rows between unbounded preceding and current row
        ) as goals,

        ps.prior_assists + sum(coalesce(sg.assists, 0)) over (
            partition by d.season, ps.player_id order by d.ranking_date
            rows between unbounded preceding and current row
        ) as assists

        -- TODO one block per new stat, as above: ps.prior_<stat> + sum(coalesce(sg.<stat>, 0)) over (...) as <stat>

    from batch_dates d
    join prior_state ps
        on ps.season = d.season
    left join skater_games sg
        on sg.season = d.season
       and sg.game_date = d.ranking_date
       and sg.player_id = ps.player_id

)

select
    season,
    ranking_date,
    player_id,
    games_played::integer                           as games_played,
    toi_seconds::integer                            as toi_seconds,
    goals::integer                                  as goals,
    assists::integer                                as assists,
    -- TODO one line per new stat: <stat>::integer as <stat>,
    -- Computed stats, from the totals
    (goals + assists)::integer                      as points,
    (select max(fetched_at) from skater_games)      as _source_fetched_at,
    current_timestamp()                             as _batch_loaded_at
from cumulative
-- A skater appears from their first game
where games_played > 0
