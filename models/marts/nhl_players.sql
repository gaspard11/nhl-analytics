{{ config(materialized='incremental', schema='marts', unique_key= 'player_id', incremental_strategy = 'merge') }}

WITH STG_GAMES_PBP AS
(
    SELECT 
        scoring_player_id, 
        assist1_player_id, 
        assist2_player_id, 
        team_id 
    FROM {{ref('stg_games_pbp')}} p
    JOIN {{ref('stg_games')}} g on p.game_id = g.game_id
    WHERE game_date = (SELECT MAX(GAME_DATE) FROM {{ref('stg_games')}})
),

CTE_PLAYER_CURRENT_TEAM AS
(
    SELECT distinct * FROM 
    (
    SELECT
        scoring_player_id as player_id,
        team_id
    FROM STG_GAMES_PBP
    UNION ALL
    SELECT
        assist1_player_id as player_id,
        team_id
    FROM STG_GAMES_PBP
    where assist1_player_id is not null
    UNION ALL
    SELECT
        assist2_player_id as player_id,
        team_id
    FROM STG_GAMES_PBP
    where assist2_player_id is not null
    )
)


select
    a.player_id,
    firstName,
    lastName,
    position,
    b.team_id,
    headshot_url
from {{ref('stg_players_info')}} a join CTE_PLAYER_CURRENT_TEAM b on a.player_id = b.player_id