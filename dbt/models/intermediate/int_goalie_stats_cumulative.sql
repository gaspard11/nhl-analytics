{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['season', 'ranking_date'],
    on_schema_change='fail'
) }}

with games as (

    select
        game_id,
        season,
        game_date
    from {{ ref('stg_nhl_api__games') }}

),

goalie_games as (

    select
        g.season,
        g.game_date,
        s.player_id,
        sum(iff(s.stat_name = 'toi_seconds', 1, 0))                   as games_played,
        sum(iff(s.stat_name = 'toi_seconds', s.stat_value, 0))        as toi_seconds,
        sum(iff(s.stat_name = 'goals_against', s.stat_value, 0))      as goals_against,
        sum(iff(s.stat_name = 'saves', s.stat_value, 0))              as saves,
        sum(iff(s.stat_name = 'shutout', s.stat_value, 0))           as shutouts,
        max(s.fetched_at)                                             as fetched_at
    from {{ ref('int_goalie_game_stats') }} s
    join games g
        on g.game_id = s.game_id
    group by g.season, g.game_date, s.player_id

),

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
-- 2a. Search: each player's last row strictly BEFORE the batch
prior_rows as (

    select
        t.season,
        t.player_id,
        t.games_played, 
        t.toi_seconds, 
        t.goals_against, 
        t.saves,
        t.shutouts
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

prior_state as (

    select
        bp.season,
        bp.player_id,
        {% if is_incremental() %}
        coalesce(p.games_played, 0)   as prior_games_played,
        coalesce(p.toi_seconds, 0) as prior_toi_seconds,
        coalesce(p.goals_against, 0) as prior_goals_against,
        coalesce(p.saves, 0) as prior_saves,
        coalesce(p.shutouts, 0) as prior_shutouts
        {% else %}
        0                                as prior_games_played,
        0                                as prior_toi_seconds,
        0                                as prior_goals_against,
        0                                as prior_saves,
        0                                as prior_shutouts
        {% endif %}
    from batch_players bp
    {% if is_incremental() %}
    left join prior_rows p
        on p.season = bp.season
       and p.player_id = bp.player_id
    {% endif %}

),

batch_dates as (

    select distinct
        g.season,
        g.game_date as ranking_date
    from games g
    join batch_start b
        on g.season = b.season
       and g.game_date >= b.from_date

),

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

        ps.prior_goals_against + sum(coalesce(gg.goals_against, 0)) over (
            partition by d.season, ps.player_id order by d.ranking_date
            rows between unbounded preceding and current row
        ) as goals_against,

        ps.prior_saves + sum(coalesce(gg.saves, 0)) over (
            partition by d.season, ps.player_id order by d.ranking_date
            rows between unbounded preceding and current row
        ) as saves,

        ps.prior_shutouts + sum(coalesce(gg.shutouts, 0)) over (
            partition by d.season, ps.player_id order by d.ranking_date
            rows between unbounded preceding and current row
        ) as shutouts

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
    goals_against::integer                           as goals_against, 
    saves::integer                                   as saves, 
    shutouts::integer                                as shutouts,
    (goals_against + saves)::integer                 as shots_against,
    goals_against * 3600 / nullif(toi_seconds, 0)    as gaa,
    saves / nullif(goals_against + saves, 0)         as save_pct,
    (select max(fetched_at) from goalie_games)  as _source_fetched_at,
    current_timestamp()                         as _batch_loaded_at
from cumulative
where games_played > 0


