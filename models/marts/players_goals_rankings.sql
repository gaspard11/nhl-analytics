{{ config(materialized='incremental', schema='marts',unique_key = ['player_id','ranking_date']) }}


WITH CTE_NEW_GOAL_SCORERS AS
(
SELECT 
    game_date,
    scoring_player_id,
    COUNT(*) as new_goals
FROM {{ref('stg_game_stats')}} a
JOIN {{ref('stg_games')}} b on a.game_id = b.game_id
GROUP BY scoring_player_id, game_date
),

CTE_PRIOR_GOAL_SCORERS AS
(
SELECT 
    ranking_date,
    player_id,
    number_of_goals
FROM {{source('nhl_marts','PLAYERS_GOALS_RANKINGS' )}}
WHERE ranking_date = (SELECT MAX(ranking_date) FROM {{source('nhl_marts','PLAYERS_GOALS_RANKINGS' )}})
),

CTE_CUMUL_GOAL_SCORERS AS
(
SELECT
    COALESCE((SELECT MAX(game_date) FROM CTE_NEW_GOAL_SCORERS),(SELECT DATEADD(day, 1, MAX(TO_DATE(ranking_date, 'YYYY-MM-DD'))) FROM CTE_PRIOR_GOAL_SCORERS)) as ranking_date,
    COALESCE(NS.scoring_player_id, PS.player_id) as player_id,
    COALESCE(NS.new_goals, 0) + COALESCE(PS.number_of_goals,0) as number_of_goals
FROM CTE_NEW_GOAL_SCORERS NS
FULL OUTER JOIN CTE_PRIOR_GOAL_SCORERS PS on NS.scoring_player_id = PS.player_id
)

SELECT
    ranking_date,
    rank() over (PARTITION BY ranking_date order by number_of_goals desc) as ranking,
    player_id,
    number_of_goals
FROM CTE_CUMUL_GOAL_SCORERS