{{ config(materialized='incremental', schema='marts', unique_key = ['player_id','ranking_date']) }}


WITH STG_GAMES AS
(
    SELECT * FROM {{ref('stg_games')}} 
    WHERE game_date = (SELECT MAX(GAME_DATE) FROM {{ref('stg_games')}})
),

STG_GAMES_PBP AS
(
    SELECT * FROM {{ref('stg_games_pbp')}} 
),

CTE_NEW_ASSISTS_RAW AS
(
SELECT 
    game_date,
    season,
    assist1_player_id as player_id,
    COUNT(*) as new_assists
FROM STG_GAMES_PBP a
JOIN STG_GAMES b on a.game_id = b.game_id
WHERE assist1_player_id is not null
GROUP BY assist1_player_id, game_date, season
UNION ALL
SELECT 
    game_date,
    season,
    assist2_player_id as player_id,
    COUNT(*) as new_assists
FROM STG_GAMES_PBP a
JOIN STG_GAMES b on a.game_id = b.game_id
WHERE assist2_player_id is not null
GROUP BY assist2_player_id, game_date, season
),
CTE_NEW_ASSISTS AS
(
SELECT 
    game_date,
    season,
    player_id,
    SUM(new_assists) as new_assists
FROM CTE_NEW_ASSISTS_RAW
GROUP BY player_id, game_date, season
),

CTE_PRIOR_ASSISTS AS
(
SELECT 
    ranking_date,
    season,
    player_id,
    number_of_assists
FROM {{ this }}
WHERE ranking_date = (SELECT MAX(ranking_date) FROM {{ this }})
),

CTE_CUMUL_ASSISTS AS
(
SELECT
    (SELECT MAX(game_date) FROM CTE_NEW_ASSISTS) as ranking_date,
    (SELECT MAX(season) FROM CTE_NEW_ASSISTS) as season,
    COALESCE(NS.player_id, PS.player_id) as player_id,
    COALESCE(NS.new_assists,0) + COALESCE(PS.number_of_assists,0) as number_of_assists
FROM CTE_NEW_ASSISTS NS
FULL OUTER JOIN CTE_PRIOR_ASSISTS PS on NS.player_id = PS.player_id
)

SELECT
    ranking_date,
    season,
    rank() over (PARTITION BY ranking_date order by number_of_assists desc) as ranking,
    player_id,
    number_of_assists
FROM CTE_CUMUL_ASSISTS


