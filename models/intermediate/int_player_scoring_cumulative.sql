{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['season', 'ranking_date'],
    on_schema_change='fail'
) }}


-- Season-to-date goals and assists per player, for every game date.
-- A player appears from the day of their first point of the season.

with games as (

    select
        game_id,
        season,
        game_date,
        fetched_at
    from {{ ref('stg_games') }}

),

-- One row per goal, with the season and date of its game.
-- A goal is "new" when its game OR its play-by-play was (re)loaded since the last run.
goals as (

    select
        g.season,
        g.game_date,
        p.game_id,
        p.scoring_player_id,
        p.assist1_player_id,
        p.assist2_player_id,
        greatest(p.fetched_at, g.fetched_at) as fetched_at
    from {{ ref('stg_games_pbp') }} p
    join games g
        on g.game_id = p.game_id

),

-- One row per player per goal event: 1 goal for the scorer, 1 assist for each assister
player_events as (

    select season, game_date, fetched_at, scoring_player_id as player_id, 1 as goals, 0 as assists
    from goals
    where scoring_player_id is not null

    union all

    select season, game_date, fetched_at, assist1_player_id as player_id, 0 as goals, 1 as assists
    from goals
    where assist1_player_id is not null

    union all

    select season, game_date, fetched_at, assist2_player_id as player_id, 0 as goals, 1 as assists
    from goals
    where assist2_player_id is not null

),

-- 1. Batch start: earliest game date among goals loaded since the last run, per season
batch_start as (

    select
        season,
        min(game_date) as from_date
    from player_events
    {% if is_incremental() %}
    where fetched_at > (
        select coalesce(max(_source_fetched_at), '1900-01-01'::timestamp) from {{ this }}
    )
    {% endif %}
    group by season

),

{% if is_incremental() %}
-- 2a. Search: each player's last row strictly BEFORE the batch
prior_rows as (

    select
        t.season,
        t.player_id,
        t.number_of_goals,
        t.number_of_assists
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

-- 2b. Players to compute: those who already had points before the batch
--     + those who score during the batch
batch_players as (

    {% if is_incremental() %}
    select season, player_id
    from prior_rows

    union
    {% endif %}

    select
        e.season,
        e.player_id
    from player_events e
    join batch_start b
        on e.season = b.season
       and e.game_date >= b.from_date

),

-- 2c. Complete list: every player gets a starting point (0 when nothing was found)
prior_state as (

    select
        bp.season,
        bp.player_id,
        {% if is_incremental() %}
        coalesce(p.number_of_goals, 0)   as prior_goals,
        coalesce(p.number_of_assists, 0) as prior_assists
        {% else %}
        0                                as prior_goals,
        0                                as prior_assists
        {% endif %}
    from batch_players bp
    {% if is_incremental() %}
    left join prior_rows p
        on p.season = bp.season
       and p.player_id = bp.player_id
    {% endif %}

),

-- 3. Days to (re)compute: every game date from the batch start onwards (no day 0 for players)
batch_dates as (

    select distinct
        g.season,
        g.game_date as ranking_date
    from games g
    join batch_start b
        on g.season = b.season
       and g.game_date >= b.from_date

),

-- 4. What each player did each day
daily as (

    select
        season,
        game_date,
        player_id,
        sum(goals)   as goals,
        sum(assists) as assists
    from player_events
    group by season, game_date, player_id

),

-- 5. New rows = starting point + running total of the daily results
cumulative as (

    select
        d.season,
        d.ranking_date,
        ps.player_id,

        ps.prior_goals + sum(coalesce(daily.goals, 0)) over (
            partition by d.season, ps.player_id order by d.ranking_date
            rows between unbounded preceding and current row
        ) as number_of_goals,

        ps.prior_assists + sum(coalesce(daily.assists, 0)) over (
            partition by d.season, ps.player_id order by d.ranking_date
            rows between unbounded preceding and current row
        ) as number_of_assists

    from batch_dates d
    join prior_state ps
        on ps.season = d.season
    left join daily
        on daily.season = d.season
       and daily.game_date = d.ranking_date
       and daily.player_id = ps.player_id

)

select
    season,
    ranking_date,
    player_id,
    number_of_goals::integer                         as number_of_goals,
    number_of_assists::integer                       as number_of_assists,
    (number_of_goals + number_of_assists)::integer   as number_of_points,
    (select max(fetched_at) from player_events)   as _source_fetched_at,
    current_timestamp()                           as _batch_loaded_at
from cumulative
-- A player appears from the day of their first point
where number_of_goals + number_of_assists > 0