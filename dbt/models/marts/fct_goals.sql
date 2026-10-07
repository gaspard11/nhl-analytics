{{ config(materialized='incremental', incremental_strategy='delete+insert', unique_key='game_id') }}

-- One row per non-shootout goal, with its situation from the scoring team's point of view.
-- A reloaded game replaces all its goals (delete+insert on game_id), so a goal disallowed
-- after the first load disappears.

with games as (

    select * from {{ ref('stg_nhl_api__games') }}

),

goals as (

    select * from {{ ref('stg_nhl_api__goals') }}

),

coded as (

    select
        goals.*,
        lpad(goals.situation_code, 4, '0')      as code,
        goals.team_id = games.home_team_id      as is_home
    from goals
    inner join games
        on goals.game_id = games.game_id

),

-- situation_code is away goalie, away skaters, home skaters, home goalie: turned around
-- to the scoring team (own) and the other team (opp)
sides as (

    select
        *,
        substr(code, iff(is_home, 4, 1), 1)::int    as own_goalie,
        substr(code, iff(is_home, 3, 2), 1)::int    as own_skaters,
        substr(code, iff(is_home, 2, 3), 1)::int    as opp_skaters,
        substr(code, iff(is_home, 1, 4), 1)::int    as opp_goalie
    from coded

)

select
    game_id,
    event_id,
    team_id,
    situation_code,
    home_score,
    away_score,
    scoring_player_id,
    assist1_player_id,
    assist2_player_id,
    period_number,
    time_in_period,
    time_remaining_in_period,
    fetched_at,
    -- A pulled goalie gives an extra skater, not a power play: it is taken off before comparing
    case
        when code in ('0101', '1010')                       then 'PS'
        when opp_goalie = 0                                 then 'EN'
        when own_skaters - (1 - own_goalie) > opp_skaters   then 'PPG'
        when own_skaters - (1 - own_goalie) < opp_skaters   then 'SHG'
        when own_goalie = 0                                 then 'EA'
        else 'EV'
    end as goal_type,
    case
        when code in ('0101', '1010') then 'Penalty shot'
        else own_skaters || ' on ' || opp_skaters
    end as strength
from sides
