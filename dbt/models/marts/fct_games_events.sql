{{ config(materialized='incremental', incremental_strategy='delete+insert', unique_key='game_id') }}

with base as (
  select
    pbp.*,
    lpad(cast(pbp.situation_code as varchar), 4, '0') as sc,
    games.home_team_id,
    games.away_team_id
  from {{ ref('stg_nhl_api__games') }} games
  join {{ ref('stg_nhl_api__pbp') }} pbp on games.game_id = pbp.game_id
),

sides as (
  select
    base.*,
    -- re-orient the code from away/home to scorer/opponent
    cast(substr(sc, 4, 1) as int) as home_goalie,
    cast(substr(sc, 3, 1) as int) as home_skaters,
    cast(substr(sc, 2, 1) as int) as away_skaters,
    cast(substr(sc, 1, 1) as int) as away_goalie
  from base
)

select
    game_id,
    event_id,
    team_id,
    situation_code,
    event_type,
    home_score,
    away_score,
    period_number,
    period_descriptor,
    time_in_period,
    time_remaining_in_period,
    zone_code,
    x_coord,
    y_coord,
    player_1_desc,
    player_1_id,
    player_2_desc,
    player_2_id,
    player_3_desc,
    player_3_id,
    goalie_in_net_id,
    details,
    case
        when sc in ('0101', '1010')                          then 'PS'
        when home_goalie = 0 or away_goalie = 0              then 'EA'
        when home_skaters + home_goalie - 1 <> away_skaters  then 'PP'
        else 'EV'
    end as situation,
    case
        when sc in ('0101', '1010') then 'Penalty shot'
        when home_skaters > away_skaters then concat(home_skaters, ' on ', away_skaters)
        else concat(away_skaters, ' on ', home_skaters)
    end as strength_adv_team,
    case
        when home_skaters > away_skaters then home_team_id
        when away_skaters > home_skaters then away_team_id
    end as man_adv_team_id,
    fetched_at
from sides
