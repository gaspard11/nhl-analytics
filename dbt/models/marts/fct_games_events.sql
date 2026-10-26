{{ config(materialized='incremental', incremental_strategy='delete+insert', unique_key='game_id') }}

WITH base AS (
  SELECT
    pbp.*,
    LPAD(CAST(pbp.situation_code AS VARCHAR), 4, '0') AS sc,
    games.home_team_id,
    games.away_team_id,
  FROM {{ ref('stg_nhl_api__games') }} games
  JOIN {{ ref('stg_nhl_api__pbp') }} pbp ON games.game_id = pbp.game_id
),

sides AS (
  SELECT
    base.*,
    -- re-orient the code from away/home to scorer/opponent
    CAST(SUBSTR(sc, 4, 1) AS INT) AS home_goalie,
    CAST(SUBSTR(sc, 3, 1) AS INT) AS home_skaters,
    CAST(SUBSTR(sc, 2, 1) AS INT) AS away_skaters,
    CAST(SUBSTR(sc, 1, 1) AS INT) AS away_goalie
  FROM base
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
    CASE
        WHEN sc IN ('0101', '1010')                          THEN 'PS'
        WHEN home_goalie = 0 OR away_goalie = 0              THEN 'EA'
        WHEN home_skaters + home_goalie - 1 <> away_skaters  THEN 'PP'
        ELSE 'EV'
    END AS situation,
    CASE
        WHEN sc IN ('0101', '1010') THEN 'Penalty shot'
        WHEN home_skaters > away_skaters THEN CONCAT(home_skaters, ' on ', away_skaters)
        ELSE CONCAT(away_skaters, ' on ', home_skaters)
    END AS strength_adv_team,
    CASE
        WHEN home_skaters > away_skaters THEN home_team_id
        WHEN away_skaters > home_skaters THEN away_team_id
    END AS man_adv_team_id,
    fetched_at
from sides