{{ config(materialized='incremental', schema='marts', unique_key = ['player_id','ranking_date']) }}


WITH CTE_NEW_ASSISTS_RAW AS
(
SELECT 
    game_date,
    assist1_player_id as player_id,
    COUNT(*) as new_assists
FROM {{ref('stg_game_stats')}} a
JOIN {{ref('stg_games')}} b on a.game_id = b.game_id
WHERE assist1_player_id is not null
GROUP BY assist1_player_id, game_date
UNION ALL
SELECT 
    game_date,
    assist2_player_id as player_id,
    COUNT(*) as new_assists
FROM {{ref('stg_game_stats')}} a
JOIN {{ref('stg_games')}} b on a.game_id = b.game_id
WHERE assist2_player_id is not null
GROUP BY assist2_player_id, game_date
),
CTE_NEW_ASSISTS AS
(
SELECT 
    game_date,
    player_id,
    SUM(new_assists) as new_assists
FROM CTE_NEW_ASSISTS_RAW
GROUP BY player_id, game_date
),

CTE_PRIOR_ASSISTS AS
(
SELECT 
    ranking_date,
    player_id,
    number_of_assists
FROM {{ this }}
WHERE ranking_date = (SELECT MAX(ranking_date) FROM {{ this }})
),

CTE_CUMUL_ASSISTS AS
(
SELECT
    COALESCE((SELECT MAX(game_date) FROM CTE_NEW_ASSISTS),(SELECT DATEADD(day, 1, MAX(TO_DATE(ranking_date, 'YYYY-MM-DD'))) FROM CTE_PRIOR_ASSISTS)) as ranking_date,
    COALESCE(NS.player_id, PS.player_id) as player_id,
    COALESCE(NS.new_assists,0) + COALESCE(PS.number_of_assists,0) as number_of_assists
FROM CTE_NEW_ASSISTS NS
FULL OUTER JOIN CTE_PRIOR_ASSISTS PS on NS.player_id = PS.player_id
)

SELECT
    ranking_date,
    rank() over (PARTITION BY ranking_date order by number_of_assists desc) as ranking,
    player_id,
    number_of_assists
FROM CTE_CUMUL_ASSISTS


