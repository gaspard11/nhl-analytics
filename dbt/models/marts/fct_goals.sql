{{ config(materialized='incremental', incremental_strategy='delete+insert', unique_key='game_id') }}

-- One row per non-shootout goal. A reloaded game replaces all its goals (delete+insert on game_id),
-- so a goal disallowed after the first load disappears.


WITH base AS (
  SELECT
    goals.*,
    LPAD(CAST(goals.situation_code AS VARCHAR), 4, '0') AS sc,
    (goals.team_id = games.home_team_id)                 AS is_home
  FROM {{ ref('stg_nhl_api__games') }} games
  JOIN {{ ref('stg_nhl_api__goals') }} goals ON games.game_id = goals.game_id
),

sides AS (
  SELECT
    base.*,
    -- re-orient the code from away/home to scorer/opponent
    CAST(CASE WHEN is_home THEN SUBSTR(sc, 4, 1) ELSE SUBSTR(sc, 1, 1) END AS INT) AS own_goalie,
    CAST(CASE WHEN is_home THEN SUBSTR(sc, 3, 1) ELSE SUBSTR(sc, 2, 1) END AS INT) AS own_skaters,
    CAST(CASE WHEN is_home THEN SUBSTR(sc, 2, 1) ELSE SUBSTR(sc, 3, 1) END AS INT) AS opp_skaters,
    CAST(CASE WHEN is_home THEN SUBSTR(sc, 1, 1) ELSE SUBSTR(sc, 4, 1) END AS INT) AS opp_goalie
  FROM base
)

SELECT
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
  CASE
    WHEN sc IN ('0101', '1010')                          THEN 'PS'
    WHEN opp_goalie = 0                                  THEN 'EN'
    WHEN own_skaters - (1 - own_goalie) > opp_skaters    THEN 'PPG'
    WHEN own_skaters - (1 - own_goalie) < opp_skaters    THEN 'SHG'
    ELSE 'EV'
  END AS goal_type,
    CASE
    WHEN sc IN ('0101', '1010') THEN 'Penalty shot'
    ELSE CONCAT(own_skaters, ' on ', opp_skaters)
    END AS strength
FROM sides