{{ config(materialized='incremental', unique_key = ['player_id','ranking_date']) }}


WITH STG_GAMES AS
(
    SELECT * FROM {{ref('stg_games')}} 
    WHERE game_date = (SELECT MAX(GAME_DATE) FROM {{ref('stg_games')}})
),

STG_GAMES_PBP AS
(
    SELECT * FROM {{ref('stg_games_pbp')}} 
),

CTE_NEW_GOAL_SCORERS AS
(
SELECT 
    game_date,
    season,
    scoring_player_id,
    COUNT(*) as new_goals
FROM STG_GAMES_PBP a
JOIN STG_GAMES b on a.game_id = b.game_id
GROUP BY scoring_player_id, game_date, season
),

CTE_PRIOR_GOAL_SCORERS AS
(
SELECT 
    ranking_date,
    season,
    player_id,
    number_of_goals
FROM {{ this }}
WHERE ranking_date = (SELECT MAX(ranking_date) FROM {{ this }})
),

CTE_CUMUL_GOAL_SCORERS AS
(
SELECT
    (SELECT MAX(game_date) FROM CTE_NEW_GOAL_SCORERS) as ranking_date,
    (SELECT MAX(season) FROM CTE_NEW_GOAL_SCORERS) as season,
    COALESCE(NS.scoring_player_id, PS.player_id) as player_id,
    COALESCE(NS.new_goals, 0) + COALESCE(PS.number_of_goals,0) as number_of_goals
FROM CTE_NEW_GOAL_SCORERS NS
FULL OUTER JOIN CTE_PRIOR_GOAL_SCORERS PS on NS.scoring_player_id = PS.player_id
)

SELECT
    ranking_date,
    season,
    rank() over (PARTITION BY ranking_date order by number_of_goals desc) as ranking,
    player_id,
    number_of_goals
FROM CTE_CUMUL_GOAL_SCORERS