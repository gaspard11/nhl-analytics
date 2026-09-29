{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['season', 'ranking_date'],
    on_schema_change='fail'
) }}

-- League standings per day. The cumulative totals come from int_league_ranking_pre_tie_breaker;
-- this model only applies the tie-breakers and ranks. Each run picks up exactly the rows the
-- upstream model (re)computed since this model's last run.

with standings as (

    select
        season,
        ranking_date,
        team_id,
        games_played,
        cumul_points,
        total_wins,
        regulation_wins,
        regulation_ot_wins,
        goals_for,
        goals_against,
        diff,
        tie_group_id,
        _batch_loaded_at
    from {{ ref('int_league_ranking_pre_tie_breaker') }}
    {% if is_incremental() %}
    where _batch_loaded_at > (
        select coalesce(max(_batch_loaded_at), '1900-01-01'::timestamp_ltz) from {{ this }}
    )
    {% endif %}

),

head_to_head as (

    select
        season,
        ranking_date,
        tie_group_id,
        team_id,
        tie_rate
    from {{ ref('int_tied_teams_rate') }}

),

standings_with_tie_rate as (

    select
        standings.*,
        coalesce(head_to_head.tie_rate, 0) as tie_rate
    from standings
    left join head_to_head
        on  head_to_head.season = standings.season
        and head_to_head.ranking_date = standings.ranking_date
        and head_to_head.tie_group_id = standings.tie_group_id
        and head_to_head.team_id = standings.team_id

)

select
    ranking_date,
    season,
    case
        -- Day 0: nobody has played yet, every team is ranked last
        when max(games_played) over (partition by season, ranking_date) = 0
            then count(*) over (partition by season, ranking_date)
        else rank() over (
            partition by season, ranking_date
            order by
                cumul_points       desc,   -- 1. points
                games_played       asc,    -- 2. fewer games played
                regulation_wins    desc,   -- 3. regulation wins
                regulation_ot_wins desc,   -- 4. regulation + OT wins
                total_wins         desc,   -- 5. total wins
                tie_rate           desc,   -- 6. head-to-head points %
                diff               desc,   -- 7. goal differential
                goals_for          desc    -- 8. goals for
        )
    end                 as ranking,
    team_id,
    cumul_points        as points,
    goals_for,
    goals_against,
    diff                as goal_diff,
    games_played,
    regulation_wins,
    regulation_ot_wins,
    total_wins,
    tie_rate,
    _batch_loaded_at
from standings_with_tie_rate
