{{ config(materialized='incremental', schema='marts', unique_key= 'player_id', incremental_strategy = 'merge') }}

WITH CTE_PLAYER_CURRENT_TEAM AS
(
    SELECT distinct * FROM 
    (
    SELECT
        scoring_player_id as player_id,
        team_id
    FROM {{ref('stg_games_pbp')}}
    UNION ALL
    SELECT
        assist1_player_id as player_id,
        team_id
    FROM {{ref('stg_games_pbp')}}
    where assist1_player_id is not null
    UNION ALL
    SELECT
        assist2_player_id as player_id,
        team_id
    FROM {{ref('stg_games_pbp')}}
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