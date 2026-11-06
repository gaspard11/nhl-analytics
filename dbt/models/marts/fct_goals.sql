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

),

-- A pulled goalie gives an extra skater, not a power play: it is taken off both sides before comparing
effective as (

    select
        *,
        own_skaters - (1 - own_goalie)              as own_effective,
        opp_skaters - (1 - opp_goalie)              as opp_effective
    from sides

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
    -- Who has more skaters. A goal into the empty net of a penalised team (5 on 5 in the code) is PP
    case
        when code in ('0101', '1010')       then 'PS'
        when own_effective > opp_effective  then 'PP'
        when own_effective < opp_effective  then 'SH'
        else 'EV'
    end as strength_situation,
    -- Which net is empty. Penalty shots first: their code has a 0 where a goalie is usually counted
    case
        when code in ('0101', '1010')       then 'NORMAL'
        when opp_goalie = 0                 then 'EN'
        when own_goalie = 0                 then 'EA'
        else 'NORMAL'
    end as net_situation,
    case
        when code in ('0101', '1010') then 'Penalty shot'
        else own_skaters || ' on ' || opp_skaters
    end as strength
from effective
