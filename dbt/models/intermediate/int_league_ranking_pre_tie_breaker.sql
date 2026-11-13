{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['season', 'ranking_date'],
    on_schema_change='fail'
) }}

-- Cumulative state table: season-to-date totals per team for every game date (plus day 0),
-- before the head-to-head tie-breaker. Each run recomputes every date from the earliest newly
-- loaded game onwards, starting from the last row before that date.

with games as (

    select * from {{ ref('int_team_game_results') }}

),

-- 1. Batch start: earliest game date among games loaded since the last run, per season
batch_start as (

    select
        season,
        min(game_date) as from_date
    from games
    {% if is_incremental() %}
    where fetched_at > (
        select coalesce(max(_source_fetched_at), '1900-01-01'::timestamp) from {{ this }}
    )
    {% endif %}
    group by season

),

{% if is_incremental() %}
-- 2a. Search: each team's last row strictly BEFORE the batch (may find nothing)
prior_rows as (

    select t.*
    from {{ this }} t
    join batch_start b
        on t.season = b.season
       and t.ranking_date < b.from_date
    qualify row_number() over (
        partition by t.season, t.team_id
        order by t.ranking_date desc
    ) = 1

),
{% endif %}

-- 2b. Complete list: every team gets a starting point (0 when nothing was found)
prior_state as (

    select
        b.season,
        b.from_date,
        teams.team_id,
        {% if is_incremental() %}
        p.team_id is not null                  as has_prior,
        coalesce(p.games_played, 0)            as prior_games_played,
        coalesce(p.cumul_points, 0)            as prior_points,
        coalesce(p.total_wins, 0)              as prior_total_wins,
        coalesce(p.regulation_wins, 0)         as prior_regulation_wins,
        coalesce(p.regulation_ot_wins, 0)      as prior_regulation_ot_wins,
        coalesce(p.goals_for, 0)               as prior_goals_for,
        coalesce(p.goals_against, 0)           as prior_goals_against,
        coalesce(p.regulation_losses, 0)       as prior_regulation_losses,
        coalesce(p.ot_losses, 0)               as prior_ot_losses,
        coalesce(p.home_wins, 0)               as prior_home_wins,
        coalesce(p.home_regulation_losses, 0)  as prior_home_regulation_losses,
        coalesce(p.home_ot_losses, 0)          as prior_home_ot_losses,
        coalesce(p.away_wins, 0)               as prior_away_wins,
        coalesce(p.away_regulation_losses, 0)  as prior_away_regulation_losses,
        coalesce(p.away_ot_losses, 0)          as prior_away_ot_losses,
        coalesce(p.shootout_wins, 0)           as prior_shootout_wins,
        coalesce(p.shootout_losses, 0)         as prior_shootout_losses
        {% else %}
        false                                  as has_prior,
        0                                      as prior_games_played,
        0                                      as prior_points,
        0                                      as prior_total_wins,
        0                                      as prior_regulation_wins,
        0                                      as prior_regulation_ot_wins,
        0                                      as prior_goals_for,
        0                                      as prior_goals_against,
        0                                      as prior_regulation_losses,
        0                                      as prior_ot_losses,
        0                                      as prior_home_wins,
        0                                      as prior_home_regulation_losses,
        0                                      as prior_home_ot_losses,
        0                                      as prior_away_wins,
        0                                      as prior_away_regulation_losses,
        0                                      as prior_away_ot_losses,
        0                                      as prior_shootout_wins,
        0                                      as prior_shootout_losses
        {% endif %}
    from batch_start b
    cross join {{ ref('nhl_teams') }} teams
    {% if is_incremental() %}
    left join prior_rows p
        on p.season = b.season
       and p.team_id = teams.team_id
    {% endif %}

),

-- 3. Days to (re)compute: every game date from the batch start onwards,
--    plus day 0 (the day before from_date) when the season has no rows yet
batch_dates as (

    select distinct
        g.season,
        g.game_date as ranking_date
    from games g
    join batch_start b
        on g.season = b.season
       and g.game_date >= b.from_date

    union

    select
        season,
        dateadd(day, -1, from_date) as ranking_date
    from prior_state
    group by season, from_date
    having max(has_prior::int) = 0

),

-- 4. What happened each day, per team
daily as (

    select
        season,
        game_date,
        team_id,
        count(*)                                  as games_played,
        sum(points)                               as points,
        sum(win)                                  as total_wins,
        sum(regulation_win)                       as regulation_wins,
        sum(regulation_ot_win)                    as regulation_ot_wins,
        sum(goals_for)                            as goals_for,
        sum(goals_against)                        as goals_against,
        sum(regulation_loss)                      as regulation_losses,
        sum(ot_loss)                              as ot_losses,
        sum(iff(is_home, win, 0))                 as home_wins,
        sum(iff(is_home, regulation_loss, 0))     as home_regulation_losses,
        sum(iff(is_home, ot_loss, 0))             as home_ot_losses,
        sum(iff(not is_home, win, 0))             as away_wins,
        sum(iff(not is_home, regulation_loss, 0)) as away_regulation_losses,
        sum(iff(not is_home, ot_loss, 0))         as away_ot_losses,
        sum(shootout_win)                         as shootout_wins,
        sum(shootout_loss)                        as shootout_losses
    from games
    group by season, game_date, team_id

),

-- 5. New rows = starting point + running total of the daily results
cumulative as (

    select
        d.season,
        d.ranking_date,
        ps.team_id,

        ps.prior_games_played + sum(coalesce(daily.games_played, 0)) over (
            partition by d.season, ps.team_id order by d.ranking_date
            rows between unbounded preceding and current row
        ) as games_played,

        ps.prior_points + sum(coalesce(daily.points, 0)) over (
            partition by d.season, ps.team_id order by d.ranking_date
            rows between unbounded preceding and current row
        ) as cumul_points,

        ps.prior_total_wins + sum(coalesce(daily.total_wins, 0)) over (
            partition by d.season, ps.team_id order by d.ranking_date
            rows between unbounded preceding and current row
        ) as total_wins,

        ps.prior_regulation_wins + sum(coalesce(daily.regulation_wins, 0)) over (
            partition by d.season, ps.team_id order by d.ranking_date
            rows between unbounded preceding and current row
        ) as regulation_wins,

        ps.prior_regulation_ot_wins + sum(coalesce(daily.regulation_ot_wins, 0)) over (
            partition by d.season, ps.team_id order by d.ranking_date
            rows between unbounded preceding and current row
        ) as regulation_ot_wins,

        ps.prior_goals_for + sum(coalesce(daily.goals_for, 0)) over (
            partition by d.season, ps.team_id order by d.ranking_date
            rows between unbounded preceding and current row
        ) as goals_for,

        ps.prior_goals_against + sum(coalesce(daily.goals_against, 0)) over (
            partition by d.season, ps.team_id order by d.ranking_date
            rows between unbounded preceding and current row
        ) as goals_against,

        ps.prior_regulation_losses + sum(coalesce(daily.regulation_losses, 0)) over (
            partition by d.season, ps.team_id order by d.ranking_date
            rows between unbounded preceding and current row
        ) as regulation_losses,

        ps.prior_ot_losses + sum(coalesce(daily.ot_losses, 0)) over (
            partition by d.season, ps.team_id order by d.ranking_date
            rows between unbounded preceding and current row
        ) as ot_losses,

        ps.prior_home_wins + sum(coalesce(daily.home_wins, 0)) over (
            partition by d.season, ps.team_id order by d.ranking_date
            rows between unbounded preceding and current row
        ) as home_wins,

        ps.prior_home_regulation_losses + sum(coalesce(daily.home_regulation_losses, 0)) over (
            partition by d.season, ps.team_id order by d.ranking_date
            rows between unbounded preceding and current row
        ) as home_regulation_losses,

        ps.prior_home_ot_losses + sum(coalesce(daily.home_ot_losses, 0)) over (
            partition by d.season, ps.team_id order by d.ranking_date
            rows between unbounded preceding and current row
        ) as home_ot_losses,

        ps.prior_away_wins + sum(coalesce(daily.away_wins, 0)) over (
            partition by d.season, ps.team_id order by d.ranking_date
            rows between unbounded preceding and current row
        ) as away_wins,

        ps.prior_away_regulation_losses + sum(coalesce(daily.away_regulation_losses, 0)) over (
            partition by d.season, ps.team_id order by d.ranking_date
            rows between unbounded preceding and current row
        ) as away_regulation_losses,

        ps.prior_away_ot_losses + sum(coalesce(daily.away_ot_losses, 0)) over (
            partition by d.season, ps.team_id order by d.ranking_date
            rows between unbounded preceding and current row
        ) as away_ot_losses,

        ps.prior_shootout_wins + sum(coalesce(daily.shootout_wins, 0)) over (
            partition by d.season, ps.team_id order by d.ranking_date
            rows between unbounded preceding and current row
        ) as shootout_wins,

        ps.prior_shootout_losses + sum(coalesce(daily.shootout_losses, 0)) over (
            partition by d.season, ps.team_id order by d.ranking_date
            rows between unbounded preceding and current row
        ) as shootout_losses

    from batch_dates d
    join prior_state ps
        on ps.season = d.season
    left join daily
        on daily.season = d.season
       and daily.game_date = d.ranking_date
       and daily.team_id = ps.team_id

),

-- 6. Last 10 games and streak: not running totals, so they are recomputed from the full game
--    history for each day of the batch. games_ago = 1 is the team's last game up to that day
recent_games as (

    select
        d.season,
        d.ranking_date,
        g.team_id,
        g.result,
        row_number() over (
            partition by d.season, d.ranking_date, g.team_id
            order by g.game_date desc, g.game_id desc
        ) as games_ago
    from batch_dates d
    join games g
        on g.season = d.season
       and g.game_date <= d.ranking_date

),

last_results as (

    select
        season,
        ranking_date,
        team_id,
        result as last_result
    from recent_games
    where games_ago = 1

),

-- The streak ends at the first game with a different result than the last one. When there is
-- none, every game played is part of it
recent_form as (

    select
        r.season,
        r.ranking_date,
        r.team_id,
        sum(iff(r.games_ago <= 10 and r.result = 'W', 1, 0))  as last_10_wins,
        sum(iff(r.games_ago <= 10 and r.result = 'L', 1, 0))  as last_10_regulation_losses,
        sum(iff(r.games_ago <= 10 and r.result = 'OT', 1, 0)) as last_10_ot_losses,
        -- The same 10 results in order, oldest first: "W,L,OT,..." (listagg skips the nulls)
        listagg(iff(r.games_ago <= 10, r.result, null), ',')
            within group (order by r.games_ago desc)           as last_10_results,
        l.last_result                                          as streak_result,
        coalesce(
            min(iff(r.result <> l.last_result, r.games_ago, null)) - 1,
            count(*)
        )                                                      as streak_length
    from recent_games r
    join last_results l
        on l.season = r.season
       and l.ranking_date = r.ranking_date
       and l.team_id = r.team_id
    group by r.season, r.ranking_date, r.team_id, l.last_result

),

-- 7. Running totals + recent form. Day 0, or a team without a game yet, has no recent form
standings as (

    select
        c.*,
        coalesce(f.last_10_wins, 0)              as last_10_wins,
        coalesce(f.last_10_regulation_losses, 0) as last_10_regulation_losses,
        coalesce(f.last_10_ot_losses, 0)         as last_10_ot_losses,
        f.last_10_results,
        f.streak_result,
        f.streak_length
    from cumulative c
    left join recent_form f
        on f.season = c.season
       and f.ranking_date = c.ranking_date
       and f.team_id = c.team_id

)

select
    season,
    ranking_date,
    team_id,
    games_played::integer                    as games_played,
    cumul_points::integer                    as cumul_points,
    total_wins::integer                      as total_wins,
    regulation_wins::integer                 as regulation_wins,
    regulation_ot_wins::integer              as regulation_ot_wins,
    goals_for::integer                       as goals_for,
    goals_against::integer                   as goals_against,
    (goals_for - goals_against)::integer     as diff,
    regulation_losses::integer               as regulation_losses,
    ot_losses::integer                       as ot_losses,
    home_wins::integer                       as home_wins,
    home_regulation_losses::integer          as home_regulation_losses,
    home_ot_losses::integer                  as home_ot_losses,
    away_wins::integer                       as away_wins,
    away_regulation_losses::integer          as away_regulation_losses,
    away_ot_losses::integer                  as away_ot_losses,
    shootout_wins::integer                   as shootout_wins,
    shootout_losses::integer                 as shootout_losses,
    last_10_wins::integer                    as last_10_wins,
    last_10_regulation_losses::integer       as last_10_regulation_losses,
    last_10_ot_losses::integer               as last_10_ot_losses,
    last_10_results,
    streak_result,
    streak_length::integer                   as streak_length,
    {{ nhl_tie_group_id(ranking_date='ranking_date') }} as tie_group_id,
    (select max(fetched_at) from games)                 as _source_fetched_at,
    current_timestamp()                                 as _batch_loaded_at
from standings