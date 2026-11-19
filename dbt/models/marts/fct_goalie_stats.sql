{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['season', 'ranking_date'],
    on_schema_change='fail'
) }}

-- Season-to-date stats per goalie, for every game date, from the goalie's first game of the season.
-- The running totals are kept here (cumulative, incremental); the per-game stats come from
-- int_player_game_stats (stats common to every player) and int_goalie_game_stats (goalie only).
-- Computed stats (shots against, GAA, save %) are computed on each row from the totals: a ratio
-- can't be added up from one game to the next.
-- Every goalie is kept, as in the full stats table on nhl.com; the app filters.

with games as (

    select
        game_id,
        season,
        game_date
    from {{ ref('stg_nhl_api__games') }}

),

goalies as (

    select player_id
    from {{ ref('dim_players') }}
    where position = 'G'

),

-- Every per-game stat of the goalies, long format
game_stats as (

    select game_id, player_id, stat_name, stat_value, fetched_at
    from {{ ref('int_player_game_stats') }}

    union all

    select game_id, player_id, stat_name, stat_value, fetched_at
    from {{ ref('int_goalie_game_stats') }}

),

-- One row per goalie per game date, one column per stat. A goalie plays at most one game a day
goalie_games as (

    select
        g.season,
        g.game_date,
        s.player_id,
        sum(iff(s.stat_name = 'toi_seconds', 1, 0))              as games_played,
        sum(iff(s.stat_name = 'toi_seconds', s.stat_value, 0))   as toi_seconds,
        sum(iff(s.stat_name = 'goals', s.stat_value, 0))         as goals,
        sum(iff(s.stat_name = 'assists', s.stat_value, 0))       as assists,
        sum(iff(s.stat_name = 'saves', s.stat_value, 0))         as saves,
        sum(iff(s.stat_name = 'goals_against', s.stat_value, 0)) as goals_against,
        sum(iff(s.stat_name = 'shutout', s.stat_value, 0))       as shutouts,
        sum(iff(s.stat_name = 'penalty_minutes', s.stat_value, 0))       as penalty_minutes,
        sum(iff(s.stat_name = 'games_started', s.stat_value, 0))       as games_started,
        sum(iff(s.stat_name = 'awarded_wins', s.stat_value, 0))      as awarded_wins,
        sum(iff(s.stat_name = 'awarded_losses', s.stat_value, 0))    as awarded_losses,
        sum(iff(s.stat_name = 'awarded_ot_losses', s.stat_value, 0)) as awarded_ot_losses,
        max(s.fetched_at)                                        as fetched_at
    from game_stats s
    join games g
        on g.game_id = s.game_id
    join goalies k
        on k.player_id = s.player_id
    group by g.season, g.game_date, s.player_id

),

-- 1. Batch start: earliest game date among games loaded since the last run, per season
batch_start as (

    select
        season,
        min(game_date) as from_date
    from goalie_games
    {% if is_incremental() %}
    where fetched_at > (
        select coalesce(max(_source_fetched_at), '1900-01-01'::timestamp) from {{ this }}
    )
    {% endif %}
    group by season

),

{% if is_incremental() %}
-- 2a. Each goalie's last row strictly BEFORE the batch
prior_rows as (

    select
        t.season,
        t.player_id,
        t.games_played,
        t.toi_seconds,
        t.goals,
        t.assists,
        t.saves,
        t.goals_against,
        t.shutouts
        t.penalty_minutes,
        t.games_started,
        t.awarded_wins,
        t.awarded_losses,
        t.awarded_ot_losses
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

-- 2b. Goalies to compute: those with a row before the batch + those who play during the batch
batch_players as (

    {% if is_incremental() %}
    select season, player_id
    from prior_rows

    union
    {% endif %}

    select distinct
        e.season,
        e.player_id
    from goalie_games e
    join batch_start b
        on e.season = b.season
       and e.game_date >= b.from_date

),

-- 2c. Every goalie gets a starting point (0 when nothing was found)
prior_state as (

    select
        bp.season,
        bp.player_id,
        {% if is_incremental() %}
        coalesce(p.games_played, 0)   as prior_games_played,
        coalesce(p.toi_seconds, 0)    as prior_toi_seconds,
        coalesce(p.goals, 0)          as prior_goals,
        coalesce(p.assists, 0)        as prior_assists,
        coalesce(p.saves, 0)          as prior_saves,
        coalesce(p.goals_against, 0)  as prior_goals_against,
        coalesce(p.shutouts, 0)       as prior_shutouts,
        coalesce(p.penalty_minutes, 0)       as prior_penalty_minutes,
        coalesce(p.games_started, 0)  as prior_games_started,
        coalesce(p.awarded_wins, 0)        as prior_awarded_wins,
        coalesce(p.awarded_losses, 0)      as prior_awarded_losses,
        coalesce(p.awarded_ot_losses, 0)   as prior_awarded_ot_losses
        {% else %}
        0                             as prior_games_played,
        0                             as prior_toi_seconds,
        0                             as prior_goals,
        0                             as prior_assists,
        0                             as prior_saves,
        0                             as prior_goals_against,
        0                             as prior_shutouts,
        0                             as prior_penalty_minutes,
        0                             as prior_games_started,
        0                                  as prior_awarded_wins,
        0                                  as prior_awarded_losses,
        0                                  as prior_awarded_ot_losses
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

        ps.prior_games_played + sum(coalesce(gg.games_played, 0)) over (
            partition by d.season, ps.player_id order by d.ranking_date
            rows between unbounded preceding and current row
        ) as games_played,

        ps.prior_toi_seconds + sum(coalesce(gg.toi_seconds, 0)) over (
            partition by d.season, ps.player_id order by d.ranking_date
            rows between unbounded preceding and current row
        ) as toi_seconds,

        ps.prior_goals + sum(coalesce(gg.goals, 0)) over (
            partition by d.season, ps.player_id order by d.ranking_date
            rows between unbounded preceding and current row
        ) as goals,

        ps.prior_assists + sum(coalesce(gg.assists, 0)) over (
            partition by d.season, ps.player_id order by d.ranking_date
            rows between unbounded preceding and current row
        ) as assists,

        ps.prior_saves + sum(coalesce(gg.saves, 0)) over (
            partition by d.season, ps.player_id order by d.ranking_date
            rows between unbounded preceding and current row
        ) as saves,

        ps.prior_goals_against + sum(coalesce(gg.goals_against, 0)) over (
            partition by d.season, ps.player_id order by d.ranking_date
            rows between unbounded preceding and current row
        ) as goals_against,

        ps.prior_shutouts + sum(coalesce(gg.shutouts, 0)) over (
            partition by d.season, ps.player_id order by d.ranking_date
            rows between unbounded preceding and current row
        ) as shutouts,

        ps.prior_penalty_minutes + sum(coalesce(gg.penalty_minutes, 0)) over (
            partition by d.season, ps.player_id order by d.ranking_date
            rows between unbounded preceding and current row
        ) as penalty_minutes,

        ps.prior_games_started + sum(coalesce(gg.games_started, 0)) over (
            partition by d.season, ps.player_id order by d.ranking_date
            rows between unbounded preceding and current row
        ) as games_started,

        ps.prior_awarded_wins + sum(coalesce(gg.awarded_wins, 0)) over (
            partition by d.season, ps.player_id order by d.ranking_date
            rows between unbounded preceding and current row
        ) as awarded_wins,

        ps.prior_awarded_losses + sum(coalesce(gg.awarded_losses, 0)) over (
            partition by d.season, ps.player_id order by d.ranking_date
            rows between unbounded preceding and current row
        ) as awarded_losses,

        ps.prior_awarded_ot_losses + sum(coalesce(gg.awarded_ot_losses, 0)) over (
            partition by d.season, ps.player_id order by d.ranking_date
            rows between unbounded preceding and current row
        ) as awarded_ot_losses

    from batch_dates d
    join prior_state ps
        on ps.season = d.season
    left join goalie_games gg
        on gg.season = d.season
       and gg.game_date = d.ranking_date
       and gg.player_id = ps.player_id

)

select
    season,
    ranking_date,
    player_id,
    games_played::integer                            as games_played,
    toi_seconds::integer                             as toi_seconds,
    goals::integer                                   as goals,
    assists::integer                                 as assists,
    saves::integer                                   as saves,
    goals_against::integer                           as goals_against,
    shutouts::integer                                as shutouts,
    penalty_minutes::integer                         as penalty_minutes,
    games_started::integer                           as games_started,
    awarded_wins::integer                            as awarded_wins,
    awarded_losses::integer                          as awarded_losses,
    awarded_ot_losses::integer                       as awarded_ot_losses,
    -- Computed stats, from the totals
    (goals_against + saves)::integer                 as shots_against,
    goals_against * 3600 / nullif(toi_seconds, 0)    as gaa,
    saves / nullif(goals_against + saves, 0)         as save_pct,
    (select max(fetched_at) from goalie_games)       as _source_fetched_at,
    current_timestamp()                              as _batch_loaded_at
from cumulative
-- A goalie appears from their first game
where games_played > 0
